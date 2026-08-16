from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from tortoise import connections

from bifrostnms.config import Settings
from bifrostnms.models import Monitor, ProbeType
from bifrostnms.schemas.dashboard import (
    DnsProbeResult,
    HttpProbeResult,
    IcmpProbeResult,
    MonitorAgentState,
    MonitorStateSummary,
    ObservationSummary,
    ProbeHistoryPoint,
    TcpProbeResult,
    TlsProbeResult,
)


def _availability_state(row: dict[str, Any], *, now: datetime, settings: Settings) -> str:
    desired_revision = int(row.get("desired_revision") or 0)
    acknowledged_revision = int(row.get("acknowledged_revision") or 0)
    if desired_revision == 0 or acknowledged_revision < desired_revision:
        return "pending_configuration"

    heartbeat = cast(datetime | None, row.get("last_heartbeat_at"))
    if heartbeat is None:
        return "agent_offline"

    heartbeat_age = (now - heartbeat).total_seconds()
    stale_after = min(
        settings.agent_offline_after_seconds,
        settings.agent_heartbeat_interval_seconds * 2,
    )
    if heartbeat_age > settings.agent_offline_after_seconds:
        return "agent_offline"
    if heartbeat_age > stale_after:
        return "agent_stale"

    interval_seconds = int(row["interval_seconds"])
    timeout_seconds = int(row["timeout_seconds"])
    grace_seconds = (
        settings.agent_heartbeat_interval_seconds
        + settings.agent_configuration_poll_interval_seconds
    )
    latest_scheduled_at = cast(datetime | None, row.get("last_scheduled_at"))
    if latest_scheduled_at is None:
        acknowledged_at = cast(datetime | None, row.get("acknowledged_at"))
        if acknowledged_at is None:
            return "no_data_yet"
        first_deadline = acknowledged_at + timedelta(
            seconds=interval_seconds + timeout_seconds + grace_seconds
        )
        return "no_data_yet" if now <= first_deadline else "overdue"

    deadline = latest_scheduled_at + timedelta(
        seconds=interval_seconds + timeout_seconds + grace_seconds
    )
    if now > deadline:
        return "overdue"

    if row.get("execution_status") == "failed":
        return "probe_error"
    if row.get("assessment") == "unhealthy":
        return "unhealthy"
    if row.get("assessment") == "healthy":
        return "healthy"
    return "probe_error"


def _headline(states: list[MonitorAgentState]) -> str:
    if not states:
        return "disabled"
    healthy = sum(item.availability_state == "healthy" for item in states)
    unhealthy = sum(item.availability_state == "unhealthy" for item in states)
    if healthy == len(states):
        return "healthy"
    if unhealthy == len(states):
        return "unhealthy"
    if healthy == 0 and unhealthy == 0:
        return "unknown"
    return "degraded"


async def query_monitor_states(
    *, realm_id: UUID, settings: Settings, now: datetime | None = None
) -> list[MonitorStateSummary]:
    resolved_now = now or datetime.now(UTC)
    connection = connections.get("default")
    rows = await connection.execute_query_dict(
        """
        WITH effective_pairs AS (
            SELECT DISTINCT
                monitor.realm_id,
                monitor.id AS monitor_id,
                monitor.name AS monitor_name,
                monitor.probe_type,
                monitor.interval_seconds,
                monitor.timeout_seconds,
                agent.id AS agent_id,
                agent.name AS agent_name
            FROM monitor
            INNER JOIN target
                ON target.id = monitor.target_id
                AND target.realm_id = monitor.realm_id
            INNER JOIN monitoragentassignment assignment
                ON assignment.monitor_id = monitor.id
                AND assignment.realm_id = monitor.realm_id
                AND assignment.enabled = TRUE
            INNER JOIN agent
                ON agent.id = assignment.agent_id
                AND agent.realm_id = monitor.realm_id
            WHERE monitor.realm_id = $1
              AND monitor.enabled = TRUE
              AND monitor.archived_at IS NULL
              AND target.enabled = TRUE
              AND target.archived_at IS NULL
              AND agent.enabled = TRUE
              AND agent.archived_at IS NULL

            UNION

            SELECT DISTINCT
                monitor.realm_id,
                monitor.id AS monitor_id,
                monitor.name AS monitor_name,
                monitor.probe_type,
                monitor.interval_seconds,
                monitor.timeout_seconds,
                agent.id AS agent_id,
                agent.name AS agent_name
            FROM monitor
            INNER JOIN target
                ON target.id = monitor.target_id
                AND target.realm_id = monitor.realm_id
            INNER JOIN monitoragentgroupassignment assignment
                ON assignment.monitor_id = monitor.id
                AND assignment.realm_id = monitor.realm_id
                AND assignment.enabled = TRUE
            INNER JOIN agentgroup
                ON agentgroup.id = assignment.agent_group_id
                AND agentgroup.realm_id = monitor.realm_id
                AND agentgroup.enabled = TRUE
                AND agentgroup.archived_at IS NULL
            INNER JOIN agentgroupmembership membership
                ON membership.agent_group_id = agentgroup.id
                AND membership.realm_id = monitor.realm_id
            INNER JOIN agent
                ON agent.id = membership.agent_id
                AND agent.realm_id = monitor.realm_id
            WHERE monitor.realm_id = $1
              AND monitor.enabled = TRUE
              AND monitor.archived_at IS NULL
              AND target.enabled = TRUE
              AND target.archived_at IS NULL
              AND agent.enabled = TRUE
              AND agent.archived_at IS NULL
        )
        SELECT
            pair.monitor_id,
            pair.monitor_name,
            pair.probe_type,
            pair.interval_seconds,
            pair.timeout_seconds,
            pair.agent_id,
            pair.agent_name,
            COALESCE(configuration.desired_revision, 0) AS desired_revision,
            COALESCE(configuration.acknowledged_revision, 0) AS acknowledged_revision,
            configuration.acknowledged_at,
            operational.last_heartbeat_at,
            latest.observation_id AS last_observation_id,
            latest.scheduled_at AS last_scheduled_at,
            latest.received_at AS last_received_at,
            latest.execution_status,
            latest.assessment
        FROM effective_pairs AS pair
        LEFT JOIN agentconfigurationstate AS configuration
            ON configuration.realm_id = pair.realm_id
            AND configuration.agent_id = pair.agent_id
        LEFT JOIN agentoperationalstate AS operational
            ON operational.realm_id = pair.realm_id
            AND operational.agent_id = pair.agent_id
        LEFT JOIN LATERAL (
            SELECT
                observation_id,
                scheduled_at,
                received_at,
                execution_status,
                assessment
            FROM observations
            WHERE realm_id = pair.realm_id
              AND monitor_id = pair.monitor_id
              AND agent_id = pair.agent_id
            ORDER BY scheduled_at DESC, received_at DESC
            LIMIT 1
        ) AS latest ON TRUE
        ORDER BY pair.monitor_name ASC, pair.agent_name ASC
        """,
        [realm_id],
    )

    grouped: dict[UUID, list[MonitorAgentState]] = defaultdict(list)
    for row in rows:
        monitor_id = UUID(str(row["monitor_id"]))
        grouped[monitor_id].append(
            MonitorAgentState(
                monitor_id=monitor_id,
                monitor_name=str(row["monitor_name"]),
                agent_id=UUID(str(row["agent_id"])),
                agent_name=str(row["agent_name"]),
                probe_type=ProbeType(str(row["probe_type"])),
                availability_state=cast(
                    Any, _availability_state(row, now=resolved_now, settings=settings)
                ),
                desired_config_revision=int(row.get("desired_revision") or 0),
                acknowledged_config_revision=int(row.get("acknowledged_revision") or 0),
                last_observation_id=(
                    UUID(str(row["last_observation_id"]))
                    if row.get("last_observation_id") is not None
                    else None
                ),
                last_scheduled_at=cast(datetime | None, row.get("last_scheduled_at")),
                last_received_at=cast(datetime | None, row.get("last_received_at")),
                execution_status=cast(Any, row.get("execution_status")),
                assessment=cast(Any, row.get("assessment")),
            )
        )

    monitors = (
        await Monitor.filter(realm_id=realm_id, archived_at=None)
        .select_related("target")
        .order_by("name")
    )
    summaries: list[MonitorStateSummary] = []
    for monitor in monitors:
        states = grouped.get(monitor.id, []) if monitor.enabled else []
        healthy_agents = sum(item.availability_state == "healthy" for item in states)
        unhealthy_agents = sum(item.availability_state == "unhealthy" for item in states)
        trustworthy = healthy_agents + unhealthy_agents
        total = len(states)
        summaries.append(
            MonitorStateSummary(
                monitor_id=monitor.id,
                monitor_name=monitor.name,
                target_id=monitor.target_id,
                target_name=monitor.target.name,
                probe_type=monitor.probe_type,
                headline=cast(Any, _headline(states)),
                effective_agents=total,
                healthy_agents=healthy_agents,
                unhealthy_agents=unhealthy_agents,
                unavailable_agents=total - trustworthy,
                coverage_percent=(trustworthy / total * 100) if total else 0,
                agents=states,
            )
        )
    return summaries


async def query_recent_observations(*, realm_id: UUID, limit: int) -> list[ObservationSummary]:
    connection = connections.get("default")
    rows = await connection.execute_query_dict(
        """
        SELECT
            observation_id,
            scheduled_at,
            received_at,
            monitor_id,
            agent_id,
            probe_type,
            execution_status,
            assessment,
            error_category,
            error_code,
            error_message
        FROM observations
        WHERE realm_id = $1
        ORDER BY received_at DESC, scheduled_at DESC
        LIMIT $2
        """,
        [realm_id, limit],
    )
    return [ObservationSummary.model_validate(row) for row in rows]


_HISTORY_SELECTS: dict[ProbeType, tuple[str, str]] = {
    ProbeType.ICMP: (
        "icmp_results",
        """
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
        """,
    ),
    ProbeType.HTTP: (
        "http_results",
        """
        result.method,
        result.scheme,
        result.status_code,
        result.redirect_count,
        result.response_size_bytes,
        result.dns_ms,
        result.connect_ms,
        result.tls_ms,
        result.ttfb_ms,
        result.total_ms,
        result.assertions_total,
        result.assertions_failed,
        result.final_url_redacted
        """,
    ),
    ProbeType.TCP: (
        "tcp_results",
        "result.port, result.address_used::text AS address_used, result.connect_ms",
    ),
    ProbeType.DNS: (
        "dns_results",
        """
        result.resolver_address::text AS resolver_address,
        result.query_name,
        result.query_type,
        result.response_code,
        result.response_ms,
        result.answer_count,
        result.answers,
        result.truncated,
        result.authoritative,
        result.assertions_total,
        result.assertions_failed
        """,
    ),
    ProbeType.TLS: (
        "tls_results",
        """
        result.port,
        result.server_name,
        result.protocol_version,
        result.cipher_suite,
        result.handshake_ms,
        result.certificate_present,
        result.hostname_valid,
        result.chain_valid,
        result.not_before,
        result.not_after,
        result.days_remaining,
        result.subject_name,
        result.issuer_name,
        result.serial_number,
        result.fingerprint_sha256
        """,
    ),
}


def _typed_result(probe_type: ProbeType, row: dict[str, Any]) -> Any | None:
    if probe_type == ProbeType.ICMP:
        if row.get("packets_sent") is None:
            return None
        return IcmpProbeResult.model_validate(row)
    if probe_type == ProbeType.HTTP:
        if row.get("method") is None:
            return None
        return HttpProbeResult.model_validate(row)
    if probe_type == ProbeType.TCP:
        if row.get("port") is None:
            return None
        return TcpProbeResult.model_validate(row)
    if probe_type == ProbeType.DNS:
        if row.get("query_name") is None:
            return None
        return DnsProbeResult.model_validate(row)
    if row.get("port") is None:
        return None
    return TlsProbeResult.model_validate(row)


async def query_probe_history(
    *,
    realm_id: UUID,
    monitor_id: UUID,
    probe_type: ProbeType,
    start: datetime,
    end: datetime,
    limit: int,
) -> list[ProbeHistoryPoint]:
    table, result_columns = _HISTORY_SELECTS[probe_type]
    connection = connections.get("default")
    rows = await connection.execute_query_dict(
        f"""
        SELECT
            observation.observation_id,
            observation.scheduled_at,
            observation.received_at,
            observation.monitor_id,
            observation.agent_id,
            observation.probe_type,
            observation.execution_status,
            observation.assessment,
            observation.error_category,
            observation.error_code,
            observation.error_message,
            {result_columns}
        FROM observations AS observation
        LEFT JOIN {table} AS result
            ON result.scheduled_at = observation.scheduled_at
            AND result.observation_id = observation.observation_id
            AND result.realm_id = observation.realm_id
            AND result.agent_id = observation.agent_id
            AND result.monitor_id = observation.monitor_id
        WHERE observation.realm_id = $1
          AND observation.monitor_id = $2
          AND observation.probe_type = $3
          AND observation.scheduled_at >= $4
          AND observation.scheduled_at <= $5
        ORDER BY observation.scheduled_at ASC, observation.agent_id ASC
        LIMIT $6
        """,
        [realm_id, monitor_id, str(probe_type), start, end, limit],
    )
    history: list[ProbeHistoryPoint] = []
    for row in rows:
        history.append(
            ProbeHistoryPoint(
                observation_id=UUID(str(row["observation_id"])),
                scheduled_at=cast(datetime, row["scheduled_at"]),
                received_at=cast(datetime, row["received_at"]),
                monitor_id=UUID(str(row["monitor_id"])),
                agent_id=UUID(str(row["agent_id"])),
                probe_type=ProbeType(str(row["probe_type"])),
                execution_status=cast(Any, row["execution_status"]),
                assessment=cast(Any, row["assessment"]),
                error_category=cast(str | None, row.get("error_category")),
                error_code=cast(str | None, row.get("error_code")),
                error_message=cast(str | None, row.get("error_message")),
                result=_typed_result(probe_type, row),
            )
        )
    return history
