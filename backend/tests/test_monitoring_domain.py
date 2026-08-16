from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise import Tortoise

from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import (
    Agent,
    AgentConfigurationSnapshot,
    AgentConfigurationState,
    AgentCredential,
    AgentGroup,
    AgentGroupMembership,
    Monitor,
    MonitorAgentAssignment,
    MonitorAgentGroupAssignment,
    ProbeType,
    Realm,
    Target,
    TargetGroup,
    TargetGroupMembership,
)
from bifrostnms.monitoring import (
    HierarchyError,
    RealmBoundaryError,
    ResourceStateError,
    add_agent_to_group,
    archive_target,
    assign_monitor_to_agent,
    assign_monitor_to_agent_group,
    create_monitor,
    effective_agent_ids,
    move_agent_group,
    update_monitor_behavior,
)


async def _delete_realm_data(realm_ids: list[object]) -> None:
    for model in (
        AgentConfigurationSnapshot,
        AgentConfigurationState,
        MonitorAgentGroupAssignment,
        MonitorAgentAssignment,
        AgentGroupMembership,
        TargetGroupMembership,
        AgentCredential,
        Monitor,
    ):
        await model.filter(realm_id__in=realm_ids).delete()
    await AgentGroup.filter(realm_id__in=realm_ids).update(parent_id=None)
    await TargetGroup.filter(realm_id__in=realm_ids).update(parent_id=None)
    for resource_model in (AgentGroup, TargetGroup, Agent, Target):
        await resource_model.filter(realm_id__in=realm_ids).delete()
    await Realm.filter(id__in=realm_ids).delete()


@pytest_asyncio.fixture
async def realms() -> AsyncIterator[tuple[Realm, Realm]]:
    await Tortoise.init(config=TORTOISE_ORM)
    suffix = uuid4().hex
    first = await Realm.create(name="First", slug=f"monitoring-first-{suffix}")
    second = await Realm.create(name="Second", slug=f"monitoring-second-{suffix}")
    try:
        yield first, second
    finally:
        await _delete_realm_data([first.id, second.id])
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_create_monitor_normalizes_configuration_and_enforces_realm(
    realms: tuple[Realm, Realm],
) -> None:
    first, second = realms
    target = await Target.create(realm=first, name="Website", address="example.com")

    monitor = await create_monitor(
        realm=first,
        target=target,
        name="HTTPS",
        probe_type=ProbeType.HTTP,
        interval_seconds=60,
        timeout_seconds=10,
        configuration={"path": "/health"},
    )

    assert monitor.configuration["schema_version"] == 1
    assert monitor.configuration["scheme"] == "https"
    with pytest.raises(RealmBoundaryError):
        await create_monitor(
            realm=second,
            target=target,
            name="Cross realm",
            probe_type=ProbeType.ICMP,
            interval_seconds=60,
            timeout_seconds=10,
            configuration={},
        )


@pytest.mark.asyncio
async def test_group_move_rejects_cycles_and_cross_realm_parents(
    realms: tuple[Realm, Realm],
) -> None:
    first, second = realms
    root = await AgentGroup.create(realm=first, name="Root")
    child = await AgentGroup.create(realm=first, name="Child", parent=root)
    foreign = await AgentGroup.create(realm=second, name="Foreign")

    with pytest.raises(HierarchyError):
        await move_agent_group(root, child)
    with pytest.raises(RealmBoundaryError):
        await move_agent_group(root, foreign)


@pytest.mark.asyncio
async def test_effective_agents_deduplicate_direct_and_group_assignments(
    realms: tuple[Realm, Realm],
) -> None:
    realm, _ = realms
    target = await Target.create(realm=realm, name="Router", address="192.0.2.1")
    monitor = await create_monitor(
        realm=realm,
        target=target,
        name="Ping",
        probe_type=ProbeType.ICMP,
        interval_seconds=30,
        timeout_seconds=5,
        configuration={},
    )
    agent = await Agent.create(realm=realm, name="London")
    group = await AgentGroup.create(realm=realm, name="United Kingdom")
    child_group = await AgentGroup.create(realm=realm, name="London", parent=group)
    child_agent = await Agent.create(realm=realm, name="London child")
    await add_agent_to_group(realm=realm, group=group, agent=agent)
    await add_agent_to_group(realm=realm, group=child_group, agent=child_agent)

    await assign_monitor_to_agent(realm=realm, monitor=monitor, agent=agent)
    await assign_monitor_to_agent_group(realm=realm, monitor=monitor, group=group)

    assert await effective_agent_ids(monitor) == {agent.id}
    state = await AgentConfigurationState.get(agent=agent)
    assert state.desired_revision == 2


@pytest.mark.asyncio
async def test_monitor_behavior_changes_increment_revisions(
    realms: tuple[Realm, Realm],
) -> None:
    realm, _ = realms
    target = await Target.create(realm=realm, name="API", address="api.example.com")
    monitor = await create_monitor(
        realm=realm,
        target=target,
        name="API health",
        probe_type=ProbeType.HTTP,
        interval_seconds=60,
        timeout_seconds=10,
        configuration={"path": "/health"},
    )
    agent = await Agent.create(realm=realm, name="Home")
    await assign_monitor_to_agent(realm=realm, monitor=monitor, agent=agent)

    unchanged = await update_monitor_behavior(
        monitor,
        realm=realm,
        target=target,
        probe_type=ProbeType.HTTP,
        interval_seconds=60,
        timeout_seconds=10,
        configuration={"path": "/health"},
    )
    assert unchanged.revision == 1

    changed = await update_monitor_behavior(
        monitor,
        realm=realm,
        target=target,
        probe_type=ProbeType.HTTP,
        interval_seconds=30,
        timeout_seconds=5,
        configuration={"path": "/ready"},
    )
    assert changed.revision == 2
    state = await AgentConfigurationState.get(agent=agent)
    assert state.desired_revision == 2


@pytest.mark.asyncio
async def test_archiving_target_archives_monitors_and_invalidates_agents(
    realms: tuple[Realm, Realm],
) -> None:
    realm, _ = realms
    target = await Target.create(realm=realm, name="Switch", address="192.0.2.2")
    monitor = await create_monitor(
        realm=realm,
        target=target,
        name="Switch ping",
        probe_type=ProbeType.ICMP,
        interval_seconds=30,
        timeout_seconds=5,
        configuration={},
    )
    agent = await Agent.create(realm=realm, name="Office")
    await assign_monitor_to_agent(realm=realm, monitor=monitor, agent=agent)

    await archive_target(realm=realm, target=target)
    await monitor.refresh_from_db()

    assert target.archived_at is not None
    assert target.enabled is False
    assert monitor.archived_at is not None
    assert monitor.enabled is False
    state = await AgentConfigurationState.get(agent=agent)
    assert state.desired_revision == 2


@pytest.mark.asyncio
async def test_archived_resources_cannot_be_assigned(
    realms: tuple[Realm, Realm],
) -> None:
    realm, _ = realms
    target = await Target.create(realm=realm, name="Server", address="192.0.2.3")
    monitor = await create_monitor(
        realm=realm,
        target=target,
        name="Server ping",
        probe_type=ProbeType.ICMP,
        interval_seconds=30,
        timeout_seconds=5,
        configuration={},
    )
    agent = await Agent.create(realm=realm, name="Archived")
    agent.archived_at = target.created_at

    with pytest.raises(ResourceStateError):
        await assign_monitor_to_agent(realm=realm, monitor=monitor, agent=agent)
