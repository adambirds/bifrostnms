from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise import Tortoise, connections

from bifrostnms.agents import AgentAuthentication, ingest_observations
from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import Agent, AgentConfigurationSnapshot, AgentCredential, Realm
from bifrostnms.schemas.agent_protocol import AgentObservationUpload


@pytest_asyncio.fixture
async def ingestion_agent() -> AsyncIterator[tuple[AgentAuthentication, str]]:
    await Tortoise.init(config=TORTOISE_ORM)
    realm = await Realm.create(name="Ingestion", slug=f"ingestion-{uuid4().hex}")
    agent = await Agent.create(realm=realm, name="Ingestion agent")
    credential = await AgentCredential.create(
        realm=realm, agent=agent, name="Ingestion", credential_hash="digest"
    )
    monitor_id = str(uuid4())
    await AgentConfigurationSnapshot.create(
        realm=realm,
        agent=agent,
        revision=1,
        content_hash="0" * 64,
        configuration={
            "monitors": [
                {
                    "monitor_id": monitor_id,
                    "monitor_revision": 2,
                    "probe_type": "icmp",
                }
            ]
        },
    )
    try:
        yield AgentAuthentication(realm=realm, agent=agent, credential=credential), monitor_id
    finally:
        connection = connections.get("default")
        await connection.execute_query("DELETE FROM icmp_results WHERE realm_id = $1", [realm.id])
        await connection.execute_query("DELETE FROM observations WHERE realm_id = $1", [realm.id])
        await AgentConfigurationSnapshot.filter(realm=realm).delete()
        await credential.delete()
        await agent.delete()
        await realm.delete()
        await Tortoise.close_connections()


def observation_upload(monitor_id: str) -> AgentObservationUpload:
    scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
    return AgentObservationUpload.model_validate(
        {
            "protocol_version": 1,
            "result_schema_version": 1,
            "agent_config_revision": 1,
            "batch_id": str(uuid4()),
            "observations": [
                {
                    "scheduled_at": scheduled_at,
                    "observation_id": str(uuid4()),
                    "monitor_id": monitor_id,
                    "monitor_revision": 2,
                    "probe_type": "icmp",
                    "started_at": scheduled_at + timedelta(milliseconds=1),
                    "finished_at": scheduled_at + timedelta(milliseconds=20),
                    "execution_status": "completed",
                    "assessment": "healthy",
                    "result": {
                        "packets_sent": 2,
                        "packets_received": 2,
                        "packet_loss_percent": 0,
                        "min_rtt_ms": 4,
                        "avg_rtt_ms": 5,
                        "median_rtt_ms": 5,
                        "max_rtt_ms": 6,
                        "p95_rtt_ms": 5.9,
                        "jitter_ms": 2,
                        "rtt_samples_ms": [4, 6],
                    },
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_ingestion_accepts_and_idempotently_acknowledges_observation(
    ingestion_agent: tuple[AgentAuthentication, str],
) -> None:
    authentication, monitor_id = ingestion_agent
    upload = observation_upload(monitor_id)

    accepted = await ingest_observations(authentication=authentication, upload=upload)
    duplicate = await ingest_observations(authentication=authentication, upload=upload)

    assert [result.disposition for result in accepted] == ["accepted"]
    assert [result.disposition for result in duplicate] == ["duplicate"]
    connection = connections.get("default")
    _, common_rows = await connection.execute_query(
        "SELECT realm_id, agent_id FROM observations WHERE observation_id = $1",
        [upload.observations[0].observation_id],
    )
    _, typed_rows = await connection.execute_query(
        "SELECT packets_received FROM icmp_results WHERE observation_id = $1",
        [upload.observations[0].observation_id],
    )
    assert len(common_rows) == 1
    assert common_rows[0]["realm_id"] == authentication.realm.id
    assert common_rows[0]["agent_id"] == authentication.agent.id
    assert len(typed_rows) == 1
    assert typed_rows[0]["packets_received"] == 2


@pytest.mark.asyncio
async def test_ingestion_rejects_conflict_and_unconfigured_monitor(
    ingestion_agent: tuple[AgentAuthentication, str],
) -> None:
    authentication, monitor_id = ingestion_agent
    upload = observation_upload(monitor_id)
    await ingest_observations(authentication=authentication, upload=upload)
    conflicting = upload.model_copy(deep=True)
    assert conflicting.observations[0].result is not None
    conflicting.observations[0].assessment = "unhealthy"
    unconfigured = observation_upload(str(uuid4()))

    conflict_results = await ingest_observations(authentication=authentication, upload=conflicting)
    unconfigured_results = await ingest_observations(
        authentication=authentication, upload=unconfigured
    )

    assert conflict_results[0].disposition == "rejected"
    assert conflict_results[0].code == "idempotency_conflict"
    assert unconfigured_results[0].code == "monitor_not_in_configuration"


@pytest.mark.asyncio
async def test_ingestion_retries_unknown_configuration_revision(
    ingestion_agent: tuple[AgentAuthentication, str],
) -> None:
    authentication, monitor_id = ingestion_agent
    upload = observation_upload(monitor_id).model_copy(update={"agent_config_revision": 999})

    results = await ingest_observations(authentication=authentication, upload=upload)

    assert results[0].disposition == "rejected"
    assert results[0].code == "configuration_revision_unavailable"
    assert results[0].retryable is True
