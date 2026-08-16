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

from bifrostnms.api.monitor_management import get_monitor, update_monitor
from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import Monitor, ProbeType, Realm, Target
from bifrostnms.schemas.monitor_management import MonitorUpdate


def request() -> Request:
    return cast(Request, SimpleNamespace())


def authorize(realm: Realm) -> AsyncMock:
    return AsyncMock(return_value=SimpleNamespace(realm=realm))


@pytest_asyncio.fixture
async def realm() -> AsyncIterator[Realm]:
    await Tortoise.init(config=TORTOISE_ORM)
    item = await Realm.create(name="Monitor management", slug=f"monitor-management-{uuid4().hex}")
    try:
        yield item
    finally:
        await Monitor.filter(realm=item).delete()
        await Target.filter(realm=item).delete()
        await item.delete()
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_get_monitor_is_realm_scoped(realm: Realm) -> None:
    target = await Target.create(realm=realm, name="Router", address="192.0.2.1")
    monitor = await Monitor.create(
        realm=realm,
        target=target,
        name="Ping",
        probe_type=ProbeType.ICMP,
        interval_seconds=60,
        timeout_seconds=10,
        configuration={"schema_version": 1},
    )

    with patch("bifrostnms.api.monitor_management.require_realm_permission", authorize(realm)):
        response = await get_monitor(monitor.id, request())

    assert response.id == monitor.id
    assert response.name == "Ping"


@pytest.mark.asyncio
async def test_update_monitor_behavior_increments_revision(realm: Realm) -> None:
    target = await Target.create(realm=realm, name="Router", address="192.0.2.1")
    monitor = await Monitor.create(
        realm=realm,
        target=target,
        name="Ping",
        probe_type=ProbeType.ICMP,
        interval_seconds=60,
        timeout_seconds=10,
        configuration={
            "schema_version": 1,
            "packet_count": 20,
            "packet_interval_ms": 50,
            "payload_size_bytes": 56,
            "address_family": "auto",
        },
    )
    payload = MonitorUpdate(
        target_id=target.id,
        name="Ping",
        description="Updated behavior",
        probe_type=ProbeType.TCP,
        interval_seconds=30,
        timeout_seconds=5,
        configuration={"schema_version": 1, "port": 443, "address_family": "auto"},
    )

    with patch("bifrostnms.api.monitor_management.require_realm_permission", authorize(realm)):
        response = await update_monitor(monitor.id, payload, request())

    assert response.probe_type == ProbeType.TCP
    assert response.interval_seconds == 30
    assert response.timeout_seconds == 5
    assert response.configuration["port"] == 443
    assert response.revision == 2
    assert response.description == "Updated behavior"


@pytest.mark.asyncio
async def test_update_monitor_metadata_does_not_increment_revision(realm: Realm) -> None:
    target = await Target.create(realm=realm, name="Router", address="192.0.2.1")
    monitor = await Monitor.create(
        realm=realm,
        target=target,
        name="Ping",
        probe_type=ProbeType.TCP,
        interval_seconds=60,
        timeout_seconds=10,
        configuration={"schema_version": 1, "port": 443, "address_family": "auto"},
    )
    payload = MonitorUpdate(
        target_id=target.id,
        name="HTTPS port",
        description="Metadata only",
        probe_type=ProbeType.TCP,
        interval_seconds=60,
        timeout_seconds=10,
        configuration=monitor.configuration,
    )

    with patch("bifrostnms.api.monitor_management.require_realm_permission", authorize(realm)):
        response = await update_monitor(monitor.id, payload, request())

    assert response.name == "HTTPS port"
    assert response.description == "Metadata only"
    assert response.revision == 1


@pytest.mark.asyncio
async def test_update_monitor_hides_cross_realm_target(realm: Realm) -> None:
    target = await Target.create(realm=realm, name="Router", address="192.0.2.1")
    monitor = await Monitor.create(
        realm=realm,
        target=target,
        name="Ping",
        probe_type=ProbeType.ICMP,
        interval_seconds=60,
        timeout_seconds=10,
        configuration={"schema_version": 1},
    )
    other = await Realm.create(name="Other", slug=f"monitor-management-other-{uuid4().hex}")
    foreign_target = await Target.create(realm=other, name="Foreign", address="192.0.2.2")
    try:
        payload = MonitorUpdate(
            target_id=foreign_target.id,
            name="Ping",
            probe_type=ProbeType.ICMP,
            interval_seconds=60,
            timeout_seconds=10,
            configuration={"schema_version": 1},
        )
        with (
            patch("bifrostnms.api.monitor_management.require_realm_permission", authorize(realm)),
            pytest.raises(HTTPException) as exc,
        ):
            await update_monitor(monitor.id, payload, request())
        assert exc.value.status_code == 404
    finally:
        await foreign_target.delete()
        await other.delete()
