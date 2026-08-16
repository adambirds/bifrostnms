from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Request
from tortoise import Tortoise

from bifrostnms.api.monitoring_relationships import (
    list_agent_group_memberships,
    list_monitor_agent_assignments,
    list_monitor_agent_group_assignments,
    list_target_group_memberships,
)
from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import (
    Agent,
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


def request() -> Request:
    return cast(Request, SimpleNamespace())


def authorize(realm: Realm) -> AsyncMock:
    return AsyncMock(return_value=SimpleNamespace(realm=realm))


@pytest_asyncio.fixture
async def realm() -> AsyncIterator[Realm]:
    await Tortoise.init(config=TORTOISE_ORM)
    item = await Realm.create(name="Relationships", slug=f"relationships-{uuid4().hex}")
    try:
        yield item
    finally:
        await MonitorAgentGroupAssignment.filter(realm=item).delete()
        await MonitorAgentAssignment.filter(realm=item).delete()
        await AgentGroupMembership.filter(realm=item).delete()
        await TargetGroupMembership.filter(realm=item).delete()
        await Monitor.filter(realm=item).delete()
        await AgentGroup.filter(realm=item).delete()
        await TargetGroup.filter(realm=item).delete()
        await Agent.filter(realm=item).delete()
        await Target.filter(realm=item).delete()
        await item.delete()
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_relationship_lists_return_realm_resources(realm: Realm) -> None:
    agent = await Agent.create(realm=realm, name="London")
    agent_group = await AgentGroup.create(realm=realm, name="United Kingdom")
    target = await Target.create(realm=realm, name="Router", address="192.0.2.1")
    target_group = await TargetGroup.create(realm=realm, name="Network")
    monitor = await Monitor.create(
        realm=realm,
        target=target,
        name="Ping",
        probe_type=ProbeType.ICMP,
        interval_seconds=30,
        timeout_seconds=5,
        configuration={"schema_version": 1},
    )
    membership = await AgentGroupMembership.create(
        realm=realm,
        agent_group=agent_group,
        agent=agent,
    )
    target_membership = await TargetGroupMembership.create(
        realm=realm,
        target_group=target_group,
        target=target,
    )
    direct = await MonitorAgentAssignment.create(
        realm=realm,
        monitor=monitor,
        agent=agent,
    )
    grouped = await MonitorAgentGroupAssignment.create(
        realm=realm,
        monitor=monitor,
        agent_group=agent_group,
    )

    with patch(
        "bifrostnms.api.monitoring_relationships.require_realm_permission", authorize(realm)
    ):
        assert [item.id for item in await list_agent_group_memberships(request())] == [
            membership.id
        ]
        assert [item.id for item in await list_target_group_memberships(request())] == [
            target_membership.id
        ]
        assert [item.id for item in await list_monitor_agent_assignments(request())] == [direct.id]
        assert [item.id for item in await list_monitor_agent_group_assignments(request())] == [
            grouped.id
        ]


@pytest.mark.asyncio
async def test_relationship_lists_do_not_cross_realm_boundaries(realm: Realm) -> None:
    other = await Realm.create(name="Other", slug=f"relationships-other-{uuid4().hex}")
    agent = await Agent.create(realm=other, name="Invisible agent")
    group = await AgentGroup.create(realm=other, name="Invisible group")
    membership = await AgentGroupMembership.create(realm=other, agent_group=group, agent=agent)
    try:
        with patch(
            "bifrostnms.api.monitoring_relationships.require_realm_permission",
            authorize(realm),
        ):
            items = await list_agent_group_memberships(request())
        assert membership.id not in {item.id for item in items}
    finally:
        await membership.delete()
        await group.delete()
        await agent.delete()
        await other.delete()
