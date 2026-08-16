from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request
from tortoise import Tortoise

from bifrostnms.api.monitoring import (
    create_agent,
    create_agent_group,
    create_agent_group_membership,
    create_monitor_agent_assignment,
    create_monitor_agent_group_assignment,
    create_monitor_endpoint,
    create_target,
    create_target_group,
    create_target_group_membership,
    delete_agent_group_membership,
    delete_monitor_agent_assignment,
    delete_monitor_agent_group_assignment,
    delete_target,
    list_agents,
    list_monitors,
    list_targets,
)
from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import (
    Agent,
    AgentConfigurationState,
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
from bifrostnms.schemas.monitoring_api import (
    AgentCreate,
    AgentGroupCreate,
    GroupCreate,
    MonitorCreate,
    TargetCreate,
)


def request() -> Request:
    return cast(Request, SimpleNamespace())


@pytest_asyncio.fixture
async def realm() -> AsyncIterator[Realm]:
    await Tortoise.init(config=TORTOISE_ORM)
    item = await Realm.create(name="API", slug=f"monitoring-api-{uuid4().hex}")
    try:
        yield item
    finally:
        await AgentConfigurationState.filter(realm=item).delete()
        await MonitorAgentGroupAssignment.filter(realm=item).delete()
        await MonitorAgentAssignment.filter(realm=item).delete()
        await AgentGroupMembership.filter(realm=item).delete()
        await TargetGroupMembership.filter(realm=item).delete()
        await Monitor.filter(realm=item).delete()
        await AgentGroup.filter(realm=item).update(parent_id=None)
        await TargetGroup.filter(realm=item).update(parent_id=None)
        await AgentGroup.filter(realm=item).delete()
        await TargetGroup.filter(realm=item).delete()
        await Agent.filter(realm=item).delete()
        await Target.filter(realm=item).delete()
        await item.delete()
        await Tortoise.close_connections()


def authorize(realm: Realm) -> AsyncMock:
    return AsyncMock(return_value=SimpleNamespace(realm=realm))


@pytest.mark.asyncio
async def test_agent_and_target_lists_are_realm_scoped(realm: Realm) -> None:
    other = await Realm.create(name="Other", slug=f"monitoring-other-{uuid4().hex}")
    try:
        with patch("bifrostnms.api.monitoring.require_realm_permission", authorize(realm)):
            agent = await create_agent(AgentCreate(name=" London "), request())
            target = await create_target(
                TargetCreate(name=" Router ", address=" 192.0.2.1 "), request()
            )
            await Agent.create(realm=other, name="Invisible")
            await Target.create(realm=other, name="Invisible", address="192.0.2.2")

            assert [item.id for item in await list_agents(request())] == [agent.id]
            assert [item.id for item in await list_targets(request())] == [target.id]
            assert agent.name == "London"
            assert target.address == "192.0.2.1"
    finally:
        await Agent.filter(realm=other).delete()
        await Target.filter(realm=other).delete()
        await other.delete()


@pytest.mark.asyncio
async def test_monitor_creation_validates_typed_configuration(realm: Realm) -> None:
    target = await Target.create(realm=realm, name="Website", address="example.com")
    authorization = authorize(realm)

    with patch("bifrostnms.api.monitoring.require_realm_permission", authorization):
        monitor = await create_monitor_endpoint(
            MonitorCreate(
                target_id=target.id,
                name="HTTPS",
                probe_type=ProbeType.HTTP,
                interval_seconds=60,
                timeout_seconds=10,
                configuration={"path": "/health"},
            ),
            request(),
        )
        assert monitor.configuration["scheme"] == "https"
        assert [item.id for item in await list_monitors(request())] == [monitor.id]

        with pytest.raises(HTTPException) as exc:
            await create_monitor_endpoint(
                MonitorCreate(
                    target_id=target.id,
                    name="Invalid",
                    probe_type=ProbeType.HTTP,
                    interval_seconds=60,
                    timeout_seconds=10,
                    configuration={"path": "health"},
                ),
                request(),
            )
        assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_monitor_creation_hides_cross_realm_target(realm: Realm) -> None:
    other = await Realm.create(name="Other", slug=f"monitoring-other-{uuid4().hex}")
    target = await Target.create(realm=other, name="Foreign", address="192.0.2.3")
    try:
        with (
            patch("bifrostnms.api.monitoring.require_realm_permission", authorize(realm)),
            pytest.raises(HTTPException) as exc,
        ):
            await create_monitor_endpoint(
                MonitorCreate(
                    target_id=target.id,
                    name="Foreign",
                    probe_type=ProbeType.ICMP,
                    interval_seconds=30,
                    timeout_seconds=5,
                ),
                request(),
            )
        assert exc.value.status_code == 404
    finally:
        await target.delete()
        await other.delete()


@pytest.mark.asyncio
async def test_delete_target_archives_it_instead_of_removing_it(realm: Realm) -> None:
    target = await Target.create(realm=realm, name="Archive", address="192.0.2.4")
    with patch("bifrostnms.api.monitoring.require_realm_permission", authorize(realm)):
        await delete_target(target.id, request())

    await target.refresh_from_db()
    assert target.archived_at is not None
    assert target.enabled is False


@pytest.mark.asyncio
async def test_group_memberships_and_assignments_are_idempotent(realm: Realm) -> None:
    auth = authorize(realm)
    target = await Target.create(realm=realm, name="Router", address="192.0.2.5")
    monitor = await Monitor.create(
        realm=realm,
        target=target,
        name="Ping",
        probe_type=ProbeType.ICMP,
        interval_seconds=30,
        timeout_seconds=5,
        configuration={"schema_version": 1},
    )
    agent = await Agent.create(realm=realm, name="London")

    with patch("bifrostnms.api.monitoring.require_realm_permission", auth):
        agent_group = await create_agent_group(AgentGroupCreate(name="United Kingdom"), request())
        target_group = await create_target_group(GroupCreate(name="Network"), request())
        membership = await create_agent_group_membership(agent_group.id, agent.id, request())
        repeated = await create_agent_group_membership(agent_group.id, agent.id, request())
        target_membership = await create_target_group_membership(
            target_group.id, target.id, request()
        )
        direct = await create_monitor_agent_assignment(monitor.id, agent.id, request())
        grouped = await create_monitor_agent_group_assignment(monitor.id, agent_group.id, request())

        assert repeated.id == membership.id
        assert target_membership.target_id == target.id
        assert direct.agent_id == agent.id
        assert grouped.agent_group_id == agent_group.id

        await delete_monitor_agent_assignment(monitor.id, agent.id, request())
        await delete_monitor_agent_group_assignment(monitor.id, agent_group.id, request())
        await delete_agent_group_membership(agent_group.id, agent.id, request())

    state = await AgentConfigurationState.get(agent=agent)
    assert state.desired_revision == 4
