from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

from bifrostnms.config import get_settings


@pytest_asyncio.fixture
async def database_connection() -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(get_settings().database_url)
    try:
        yield connection
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_measurement_tables_are_seven_day_hypertables(
    database_connection: asyncpg.Connection,
) -> None:
    rows = await database_connection.fetch(
        """
        SELECT hypertable_name
        FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'public'
        ORDER BY hypertable_name
        """
    )

    assert {row["hypertable_name"] for row in rows} >= {
        "observations",
        "icmp_results",
        "http_results",
        "tcp_results",
        "dns_results",
        "tls_results",
    }

    dimensions = await database_connection.fetch(
        """
        SELECT hypertable_name, time_interval
        FROM timescaledb_information.dimensions
        WHERE hypertable_schema = 'public'
          AND hypertable_name IN (
              'observations', 'icmp_results', 'http_results',
              'tcp_results', 'dns_results', 'tls_results'
          )
        """
    )
    assert {row["time_interval"] for row in dimensions} == {timedelta(days=7)}


async def _insert_observation(
    connection: asyncpg.Connection, scheduled_at: datetime, observation_id: UUID
) -> None:
    await connection.execute(
        """
        INSERT INTO observations (
            scheduled_at, observation_id, realm_id, agent_id, monitor_id,
            probe_type, monitor_revision, agent_config_revision, started_at,
            finished_at, execution_status, assessment
        ) VALUES (
            $1, $2, $3, $4, $5, 'icmp', 1, 1, $6, $7, 'completed', 'healthy'
        )
        """,
        scheduled_at,
        observation_id,
        uuid4(),
        uuid4(),
        uuid4(),
        scheduled_at,
        scheduled_at + timedelta(milliseconds=50),
    )


@pytest.mark.asyncio
async def test_observation_identity_is_idempotent_within_scheduled_time(
    database_connection: asyncpg.Connection,
) -> None:
    scheduled_at = datetime.now(UTC)
    observation_id = uuid4()
    try:
        await _insert_observation(database_connection, scheduled_at, observation_id)
        with pytest.raises(asyncpg.UniqueViolationError):
            await _insert_observation(database_connection, scheduled_at, observation_id)
    finally:
        await database_connection.execute(
            "DELETE FROM observations WHERE scheduled_at = $1 AND observation_id = $2",
            scheduled_at,
            observation_id,
        )


@pytest.mark.asyncio
async def test_icmp_result_enforces_sample_and_packet_counts(
    database_connection: asyncpg.Connection,
) -> None:
    scheduled_at = datetime.now(UTC)
    with pytest.raises(asyncpg.CheckViolationError):
        await database_connection.execute(
            """
            INSERT INTO icmp_results (
                scheduled_at, observation_id, realm_id, agent_id, monitor_id,
                packets_sent, packets_received, packet_loss_percent, rtt_samples_ms
            ) VALUES ($1, $2, $3, $4, $5, 3, 2, 33.333, ARRAY[12.5])
            """,
            scheduled_at,
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )


@pytest.mark.asyncio
async def test_graph_indexes_are_realm_led(
    database_connection: asyncpg.Connection,
) -> None:
    index_definitions = await database_connection.fetch(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname LIKE '%_realm_monitor_agent_scheduled_idx'
        """
    )

    assert len(index_definitions) == 6
    assert all(
        "(realm_id, monitor_id, agent_id, scheduled_at DESC)" in row["indexdef"]
        for row in index_definitions
    )
