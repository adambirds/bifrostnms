from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise import Tortoise

from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import (
    Agent,
    AgentConfigurationState,
    AgentGroup,
    Monitor,
    MonitorAgentGroupAssignment,
    ProbeType,
    Realm,
    Target,
    TargetGroup,
    TargetGroupMembership,
)
from bifrostnms.monitoring.bulk import create_monitors_bulk
from bifrostnms.schemas.monitoring_api import BulkMonitorCreate


@pytest_asyncio.fixture
async def realm() -> AsyncIterator[Realm]:
    await Tortoise.init(config=TORTOISE_ORM)
    suffix = uuid4().hex
    realm = await Realm.create(name="Bulk", slug=f"bulk-monitor-{suffix}")
    try:
        yield realm
    finally:
        await AgentConfigurationState.filter(realm=realm).delete()
        await MonitorAgentGroupAssignment.filter(realm=realm).delete()
        await TargetGroupMembership.filter(realm=realm).delete()
        await Monitor.filter(realm=realm).delete()
        await AgentGroup.filter(realm=realm).delete()
        await Agent.filter(realm=realm).delete()
        await TargetGroup.filter(realm=realm).delete()
        await Target.filter(realm=realm).delete()
        await realm.delete()
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_bulk_create_applies_monitor_to_target_group(realm: Realm) -> None:
    first = await Target.create(realm=realm, name="First", address="first.example.com")
    second = await Target.create(realm=realm, name="Second", address="second.example.com")
    group = await TargetGroup.create(realm=realm, name="Websites")
    await TargetGroupMembership.create(realm=realm, target_group=group, target=first)
    await TargetGroupMembership.create(realm=realm, target_group=group, target=second)
    agent = await Agent.create(realm=realm, name="Manchester")
    agent_group = await AgentGroup.create(realm=realm, name="UK Agents")

    created, skipped = await create_monitors_bulk(
        realm=realm,
        payload=BulkMonitorCreate(
            target_group_id=group.id,
            name_template="{target} - {probe}",
            probe_type=ProbeType.ICMP,
            interval_seconds=30,
            timeout_seconds=5,
            configuration={},
            agent_group_ids=[agent_group.id],
        ),
    )

    assert skipped == []
    assert [monitor.name for monitor in created] == ["First - ICMP", "Second - ICMP"]
    assert {monitor.target_id for monitor in created} == {first.id, second.id}
    assert await MonitorAgentGroupAssignment.filter(
        realm=realm,
        agent_group=agent_group,
    ).count() == 2
    assert await AgentConfigurationState.filter(realm=realm, agent=agent).count() == 0


@pytest.mark.asyncio
async def test_bulk_create_can_duplicate_and_skip_equivalent_monitor(realm: Realm) -> None:
    source_target = await Target.create(
        realm=realm,
        name="Source",
        address="source.example.com",
    )
    destination = await Target.create(
        realm=realm,
        name="Destination",
        address="destination.example.com",
    )
    source = await Monitor.create(
        realm=realm,
        target=source_target,
        name="Baseline ping",
        probe_type=ProbeType.ICMP,
        interval_seconds=30,
        timeout_seconds=5,
        configuration={
            "schema_version": 1,
            "packet_count": 20,
            "packet_interval_ms": 50,
            "per_packet_timeout_ms": 4050,
            "payload_size_bytes": 56,
            "address_family": "auto",
            "maximum_packet_loss_percent": None,
            "maximum_average_rtt_ms": None,
        },
    )

    payload = BulkMonitorCreate(
        target_ids=[destination.id],
        source_monitor_id=source.id,
        name_template="{target} - {source}",
    )
    created, skipped = await create_monitors_bulk(realm=realm, payload=payload)
    assert skipped == []
    assert len(created) == 1
    assert created[0].name == "Destination - Baseline ping"
    assert created[0].configuration == source.configuration

    repeated, repeated_skipped = await create_monitors_bulk(realm=realm, payload=payload)
    assert repeated == []
    assert len(repeated_skipped) == 1
    assert "equivalent monitor" in repeated_skipped[0].reason
