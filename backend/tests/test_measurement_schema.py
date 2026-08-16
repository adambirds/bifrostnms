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


@pytest.mark.asyncio
async def test_representative_queries_use_realm_scoped_indexes(
    database_connection: asyncpg.Connection,
) -> None:
    realm_id = uuid4()
    other_realm_id = uuid4()
    agent_id = uuid4()
    monitor_id = uuid4()
    transaction = database_connection.transaction()
    await transaction.start()
    try:
        await database_connection.execute(
            """
            INSERT INTO observations (
                scheduled_at, observation_id, realm_id, agent_id, monitor_id,
                probe_type, monitor_revision, agent_config_revision, started_at,
                finished_at, execution_status, assessment
            )
            SELECT
                CURRENT_TIMESTAMP - make_interval(mins => value),
                md5(($1::uuid)::text || value::text)::uuid,
                CASE WHEN value % 2 = 0 THEN $1::uuid ELSE $2::uuid END,
                CASE WHEN value % 5 = 0
                    THEN $3::uuid ELSE md5('agent' || value::text)::uuid END,
                CASE WHEN value % 20 = 0
                    THEN $4::uuid ELSE md5('monitor' || value::text)::uuid END,
                'icmp', 1, 1,
                CURRENT_TIMESTAMP - make_interval(mins => value),
                CURRENT_TIMESTAMP - make_interval(mins => value) + INTERVAL '10 ms',
                'completed',
                CASE WHEN value % 10 = 0 THEN 'unhealthy' ELSE 'healthy' END
            FROM generate_series(1, 4000) AS value
            """,
            realm_id,
            other_realm_id,
            agent_id,
            monitor_id,
        )
        await database_connection.execute(
            """
            INSERT INTO icmp_results (
                scheduled_at, observation_id, realm_id, agent_id, monitor_id,
                packets_sent, packets_received, packet_loss_percent,
                min_rtt_ms, avg_rtt_ms, median_rtt_ms, max_rtt_ms,
                p95_rtt_ms, jitter_ms, rtt_samples_ms
            )
            SELECT
                CURRENT_TIMESTAMP - make_interval(mins => value),
                md5(($1::uuid)::text || value::text)::uuid,
                CASE WHEN value % 2 = 0 THEN $1::uuid ELSE $2::uuid END,
                CASE WHEN value % 5 = 0
                    THEN $3::uuid ELSE md5('agent' || value::text)::uuid END,
                CASE WHEN value % 20 = 0
                    THEN $4::uuid ELSE md5('monitor' || value::text)::uuid END,
                3, 3, 0, 10, 11, 11, 12, 12, 1, ARRAY[10, 11, 12]::double precision[]
            FROM generate_series(1, 4000) AS value
            """,
            realm_id,
            other_realm_id,
            agent_id,
            monitor_id,
        )
        await database_connection.execute("ANALYZE observations; ANALYZE icmp_results")
        # Chunk statistics are deliberately small and fluctuate between tests.
        # Disable sequential scans here to prove each reviewed query shape is
        # compatible with its intended realm-led index on every selected chunk.
        await database_connection.execute("SET LOCAL enable_seqscan = off")

        graph_plan = await database_connection.fetchval(
            """
            EXPLAIN (FORMAT JSON)
            SELECT scheduled_at, assessment
            FROM observations
            WHERE realm_id = $1 AND monitor_id = $2 AND agent_id = $3
              AND scheduled_at >= CURRENT_TIMESTAMP - INTERVAL '3 days'
            ORDER BY scheduled_at DESC
            """,
            realm_id,
            monitor_id,
            agent_id,
        )
        assessment_plan = await database_connection.fetchval(
            """
            EXPLAIN (FORMAT JSON)
            SELECT scheduled_at, monitor_id
            FROM observations
            WHERE realm_id = $1 AND assessment = 'unhealthy'
              AND scheduled_at >= CURRENT_TIMESTAMP - INTERVAL '3 days'
            ORDER BY scheduled_at DESC
            """,
            realm_id,
        )
        icmp_plan = await database_connection.fetchval(
            """
            EXPLAIN (FORMAT JSON)
            SELECT scheduled_at, packet_loss_percent, rtt_samples_ms
            FROM icmp_results
            WHERE realm_id = $1 AND monitor_id = $2 AND agent_id = $3
              AND scheduled_at >= CURRENT_TIMESTAMP - INTERVAL '3 days'
            ORDER BY scheduled_at DESC
            """,
            realm_id,
            monitor_id,
            agent_id,
        )

        assert "observations_realm_monitor_agent_scheduled_idx" in str(graph_plan)
        assert "observations_realm_assessment_scheduled_idx" in str(assessment_plan)
        assert "Index Scan" in str(icmp_plan)
        assert all(column in str(icmp_plan) for column in ("realm_id", "monitor_id", "agent_id"))
    finally:
        await transaction.rollback()
