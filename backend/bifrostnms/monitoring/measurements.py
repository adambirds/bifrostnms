from __future__ import annotations

from datetime import datetime
from uuid import UUID

from tortoise import connections

from bifrostnms.schemas.monitoring_api import IcmpHistoryPoint


async def query_icmp_history(
    *, realm_id: UUID, monitor_id: UUID, start: datetime, end: datetime, limit: int
) -> list[IcmpHistoryPoint]:
    connection = connections.get("default")
    rows = await connection.execute_query_dict(
        """
        SELECT
            observation.scheduled_at,
            observation.agent_id,
            observation.assessment,
            result.packets_sent,
            result.packets_received,
            result.packet_loss_percent,
            result.min_rtt_ms,
            result.avg_rtt_ms,
            result.median_rtt_ms,
            result.max_rtt_ms,
            result.p95_rtt_ms,
            result.jitter_ms,
            result.rtt_samples_ms
        FROM observations AS observation
        INNER JOIN icmp_results AS result
            ON result.scheduled_at = observation.scheduled_at
            AND result.observation_id = observation.observation_id
            AND result.realm_id = observation.realm_id
            AND result.agent_id = observation.agent_id
            AND result.monitor_id = observation.monitor_id
        WHERE observation.realm_id = $1
          AND observation.monitor_id = $2
          AND observation.probe_type = 'icmp'
          AND observation.scheduled_at >= $3
          AND observation.scheduled_at <= $4
        ORDER BY observation.scheduled_at ASC, observation.agent_id ASC
        LIMIT $5
        """,
        [realm_id, monitor_id, start, end, limit],
    )
    return [IcmpHistoryPoint.model_validate(row) for row in rows]
