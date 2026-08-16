from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise import Tortoise

from bifrostnms.agents import (
    AgentAuthentication,
    AgentProtocolError,
    acknowledge_configuration,
    get_or_create_configuration,
)
from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import (
    Agent,
    AgentConfigurationSnapshot,
    AgentConfigurationState,
    AgentCredential,
    AgentOperationalState,
    Monitor,
    MonitorAgentAssignment,
    ProbeType,
    Realm,
    Target,
)


@pytest_asyncio.fixture
async def configured_agent() -> AsyncIterator[tuple[AgentAuthentication, Monitor]]:
    await Tortoise.init(config=TORTOISE_ORM)
    realm = await Realm.create(name="Configuration", slug=f"config-{uuid4().hex}")
    agent = await Agent.create(realm=realm, name="London")
    credential = await AgentCredential.create(
        realm=realm, agent=agent, name="Configuration", credential_hash="digest"
    )
    target = await Target.create(realm=realm, name="Router", address="192.0.2.1")
    monitor = await Monitor.create(
        realm=realm,
        target=target,
        name="Ping",
        probe_type=ProbeType.ICMP,
        interval_seconds=30,
        timeout_seconds=5,
        configuration={"schema_version": 1, "packet_count": 5},
    )
    await MonitorAgentAssignment.create(realm=realm, monitor=monitor, agent=agent)
    await AgentConfigurationState.create(realm=realm, agent=agent, desired_revision=1)
    await AgentOperationalState.create(
        realm=realm,
        agent=agent,
        last_heartbeat_at=datetime.now(UTC),
        agent_version="0.1.0",
        platform="linux",
        architecture="amd64",
        hostname="config-agent",
        capabilities={"probes": {"icmp": {"schema_versions": [1], "available": True}}},
        database_health="healthy",
        scheduler_state="running",
        agent_time=datetime.now(UTC),
        clock_offset_ms=0,
    )
    authentication = AgentAuthentication(realm=realm, agent=agent, credential=credential)
    try:
        yield authentication, monitor
    finally:
        await AgentConfigurationSnapshot.filter(realm=realm).delete()
        await AgentOperationalState.filter(realm=realm).delete()
        await AgentConfigurationState.filter(realm=realm).delete()
        await MonitorAgentAssignment.filter(realm=realm).delete()
        await credential.delete()
        await monitor.delete()
        await agent.delete()
        await target.delete()
        await realm.delete()
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_configuration_snapshot_is_deterministic_and_immutable(
    configured_agent: tuple[AgentAuthentication, Monitor],
) -> None:
    authentication, monitor = configured_agent
    first = await get_or_create_configuration(authentication)
    second = await get_or_create_configuration(authentication)

    assert second.snapshot.id == first.snapshot.id
    assert second.snapshot.content_hash == first.snapshot.content_hash
    assert await AgentConfigurationSnapshot.filter(agent=authentication.agent).count() == 1
    assert first.content["monitors"] == [
        {
            "monitor_id": str(monitor.id),
            "target_id": str(monitor.target_id),
            "monitor_revision": 1,
            "target_address": "192.0.2.1",
            "probe_type": "icmp",
            "probe_schema_version": 1,
            "interval_seconds": 30,
            "timeout_seconds": 5,
            "missed_run_policy": "skip",
            "configuration": {"schema_version": 1, "packet_count": 5},
        }
    ]


@pytest.mark.asyncio
async def test_configuration_rejects_unsupported_assigned_probe(
    configured_agent: tuple[AgentAuthentication, Monitor],
) -> None:
    authentication, _ = configured_agent
    state = await AgentOperationalState.get(agent=authentication.agent)
    state.capabilities = {"probes": {}}
    await state.save(update_fields=["capabilities"])

    with pytest.raises(AgentProtocolError) as exc:
        await get_or_create_configuration(authentication)
    assert exc.value.code == "incompatible_capability"
    assert await AgentConfigurationSnapshot.filter(agent=authentication.agent).count() == 0


@pytest.mark.asyncio
async def test_configuration_acknowledgement_is_validated_and_idempotent(
    configured_agent: tuple[AgentAuthentication, Monitor],
) -> None:
    authentication, _ = configured_agent
    result = await get_or_create_configuration(authentication)
    activated_at = datetime.now(UTC)
    state = await acknowledge_configuration(
        authentication=authentication,
        revision=result.snapshot.revision,
        content_hash=f"sha256:{result.snapshot.content_hash}",
        activated_at=activated_at,
    )
    repeated = await acknowledge_configuration(
        authentication=authentication,
        revision=result.snapshot.revision,
        content_hash=f"sha256:{result.snapshot.content_hash}",
        activated_at=activated_at,
    )
    assert repeated.acknowledged_revision == state.acknowledged_revision == 1
    assert repeated.acknowledged_content_hash == result.snapshot.content_hash

    with pytest.raises(AgentProtocolError) as exc:
        await acknowledge_configuration(
            authentication=authentication,
            revision=2,
            content_hash=f"sha256:{'0' * 64}",
            activated_at=activated_at,
        )
    assert exc.value.code == "unknown_configuration"
