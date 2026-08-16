from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise import Tortoise

from bifrostnms.agents import AgentAuthentication, record_heartbeat
from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import (
    Agent,
    AgentConfigurationState,
    AgentCredential,
    AgentOperationalState,
    Realm,
)
from bifrostnms.schemas.agent_protocol import (
    AgentCapabilities,
    AgentHeartbeatRequest,
    DatabaseHealth,
    ProbeCapability,
    SchedulerState,
)


@pytest_asyncio.fixture
async def agent_authentication() -> AsyncIterator[AgentAuthentication]:
    await Tortoise.init(config=TORTOISE_ORM)
    realm = await Realm.create(name="Heartbeat", slug=f"heartbeat-{uuid4().hex}")
    agent = await Agent.create(realm=realm, name="London")
    credential = await AgentCredential.create(
        realm=realm, agent=agent, name="Heartbeat", credential_hash="digest"
    )
    try:
        yield AgentAuthentication(realm=realm, agent=agent, credential=credential)
    finally:
        await AgentOperationalState.filter(realm=realm).delete()
        await AgentConfigurationState.filter(realm=realm).delete()
        await credential.delete()
        await agent.delete()
        await realm.delete()
        await Tortoise.close_connections()


def heartbeat_payload(*, queue_depth: int = 3) -> AgentHeartbeatRequest:
    return AgentHeartbeatRequest(
        protocol_version=1,
        agent_version="0.1.0",
        platform="linux",
        architecture="amd64",
        hostname="monitor-1",
        capabilities=AgentCapabilities(
            probes={"icmp": ProbeCapability(schema_versions=[1], available=True)},
            runtime={"raw_socket": True, "ipv4": True},
        ),
        active_configuration_revision=2,
        known_desired_configuration_revision=3,
        queue_depth=queue_depth,
        queue_bytes=1024,
        oldest_pending_observation_at=datetime.now(UTC) - timedelta(minutes=1),
        database_health=DatabaseHealth.HEALTHY,
        scheduler_state=SchedulerState.RUNNING,
        agent_time=datetime.now(UTC) - timedelta(milliseconds=50),
        warnings=["Observation upload is delayed"],
    )


@pytest.mark.asyncio
async def test_heartbeat_records_bounded_operational_state(
    agent_authentication: AgentAuthentication,
) -> None:
    state, configuration = await record_heartbeat(
        authentication=agent_authentication,
        payload=heartbeat_payload(),
    )

    assert state.realm_id == agent_authentication.realm.id
    assert state.agent_id == agent_authentication.agent.id
    assert state.capabilities["probes"]["icmp"]["schema_versions"] == [1]
    assert state.queue_depth == 3
    assert state.clock_offset_ms >= 0
    assert configuration.desired_revision == 0


@pytest.mark.asyncio
async def test_heartbeat_updates_one_latest_state_record(
    agent_authentication: AgentAuthentication,
) -> None:
    first, _ = await record_heartbeat(
        authentication=agent_authentication, payload=heartbeat_payload(queue_depth=4)
    )
    second, _ = await record_heartbeat(
        authentication=agent_authentication, payload=heartbeat_payload(queue_depth=0)
    )

    assert second.id == first.id
    assert second.queue_depth == 0
    assert await AgentOperationalState.filter(agent=agent_authentication.agent).count() == 1


def test_heartbeat_rejects_unbounded_warnings() -> None:
    data = heartbeat_payload().model_dump()
    data["warnings"] = ["x" * 501]
    with pytest.raises(ValueError):
        AgentHeartbeatRequest.model_validate(data)
