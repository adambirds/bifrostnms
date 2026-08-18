from __future__ import annotations

from collections import defaultdict
from typing import Any, cast
from uuid import UUID

from tortoise import connections

from bifrostnms.config import Settings
from bifrostnms.models import Agent, Monitor, ProbeType, Target
from bifrostnms.monitoring.dashboard import _typed_result, query_monitor_states
from bifrostnms.schemas.dashboard import (
    Assessment,
    DashboardOverview,
    ExecutionStatus,
    MonitorHeadline,
    ProbeResult,
    TargetMonitorSummary,
    TargetOperationalSummary,
)


def _target_headline(monitors: list[TargetMonitorSummary], *, enabled: bool) -> MonitorHeadline:
    if not enabled:
        return "disabled"
    if not monitors:
        return "unknown"
    headlines = [monitor.headline for monitor in monitors]
    if "unhealthy" in headlines:
        return "unhealthy"
    if "degraded" in headlines:
        return "degraded"
    if all(headline == "healthy" for headline in headlines):
        return "healthy"
    return "unknown"


async def _latest_results(*, realm_id: UUID) -> dict[UUID, dict[str, Any]]:
    connection = connections.get("default")
    rows = await connection.execute_query_dict(
        """
        SELECT DISTINCT ON (observation.monitor_id)
            observation.monitor_id,
            observation.scheduled_at,
            observation.agent_id,
            agent.name AS agent_name,
            observation.probe_type,
            observation.execution_status,
            observation.assessment,
            observation.error_code,
            CASE observation.probe_type
                WHEN 'icmp' THEN to_jsonb(icmp_result)
                WHEN 'http' THEN to_jsonb(http_result)
                WHEN 'tcp' THEN to_jsonb(tcp_result)
                WHEN 'dns' THEN to_jsonb(dns_result)
                WHEN 'tls' THEN to_jsonb(tls_result)
                ELSE NULL
            END AS result
        FROM observations AS observation
        LEFT JOIN agent
            ON agent.id = observation.agent_id
            AND agent.realm_id = observation.realm_id
        LEFT JOIN icmp_results AS icmp_result
            ON observation.probe_type = 'icmp'
            AND icmp_result.scheduled_at = observation.scheduled_at
            AND icmp_result.observation_id = observation.observation_id
        LEFT JOIN http_results AS http_result
            ON observation.probe_type = 'http'
            AND http_result.scheduled_at = observation.scheduled_at
            AND http_result.observation_id = observation.observation_id
        LEFT JOIN tcp_results AS tcp_result
            ON observation.probe_type = 'tcp'
            AND tcp_result.scheduled_at = observation.scheduled_at
            AND tcp_result.observation_id = observation.observation_id
        LEFT JOIN dns_results AS dns_result
            ON observation.probe_type = 'dns'
            AND dns_result.scheduled_at = observation.scheduled_at
            AND dns_result.observation_id = observation.observation_id
        LEFT JOIN tls_results AS tls_result
            ON observation.probe_type = 'tls'
            AND tls_result.scheduled_at = observation.scheduled_at
            AND tls_result.observation_id = observation.observation_id
        WHERE observation.realm_id = $1
        ORDER BY observation.monitor_id, observation.scheduled_at DESC, observation.received_at DESC
        """,
        [realm_id],
    )
    return {UUID(str(row["monitor_id"])): row for row in rows}


async def query_target_summaries(
    *, realm_id: UUID, settings: Settings
) -> list[TargetOperationalSummary]:
    states = await query_monitor_states(realm_id=realm_id, settings=settings)
    states_by_monitor = {state.monitor_id: state for state in states}
    latest_by_monitor = await _latest_results(realm_id=realm_id)

    monitors = await Monitor.filter(realm_id=realm_id, archived_at=None).order_by("name")
    monitors_by_target: dict[UUID, list[Monitor]] = defaultdict(list)
    for monitor in monitors:
        monitors_by_target[monitor.target_id].append(monitor)

    targets = await Target.filter(realm_id=realm_id, archived_at=None).order_by("name")
    summaries: list[TargetOperationalSummary] = []
    for target in targets:
        monitor_summaries: list[TargetMonitorSummary] = []
        agent_ids: set[UUID] = set()
        for monitor in monitors_by_target.get(target.id, []):
            state = states_by_monitor.get(monitor.id)
            latest = latest_by_monitor.get(monitor.id)
            latest_result: ProbeResult | None = None
            latest_probe_type = monitor.probe_type
            if latest is not None:
                latest_probe_type = ProbeType(str(latest["probe_type"]))
                latest_result = _typed_result(latest_probe_type, latest)
            if state is not None:
                agent_ids.update(agent.agent_id for agent in state.agents)
            monitor_summaries.append(
                TargetMonitorSummary(
                    monitor_id=monitor.id,
                    monitor_name=monitor.name,
                    probe_type=monitor.probe_type,
                    headline=state.headline if state is not None else "unknown",
                    enabled=monitor.enabled,
                    effective_agents=state.effective_agents if state is not None else 0,
                    healthy_agents=state.healthy_agents if state is not None else 0,
                    unhealthy_agents=state.unhealthy_agents if state is not None else 0,
                    unavailable_agents=state.unavailable_agents if state is not None else 0,
                    coverage_percent=state.coverage_percent if state is not None else 0,
                    latest_scheduled_at=cast(Any, latest.get("scheduled_at")) if latest else None,
                    latest_agent_id=(
                        UUID(str(latest["agent_id"]))
                        if latest is not None and latest.get("agent_id") is not None
                        else None
                    ),
                    latest_agent_name=(
                        str(latest["agent_name"])
                        if latest is not None and latest.get("agent_name") is not None
                        else None
                    ),
                    latest_assessment=(
                        cast(Assessment, latest["assessment"])
                        if latest is not None and latest.get("assessment") is not None
                        else None
                    ),
                    latest_execution_status=(
                        cast(ExecutionStatus, latest["execution_status"])
                        if latest is not None and latest.get("execution_status") is not None
                        else None
                    ),
                    latest_error_code=(
                        str(latest["error_code"])
                        if latest is not None and latest.get("error_code") is not None
                        else None
                    ),
                    latest_result=latest_result,
                )
            )

        headline = _target_headline(monitor_summaries, enabled=target.enabled)
        summaries.append(
            TargetOperationalSummary(
                target_id=target.id,
                target_name=target.name,
                address=target.address,
                description=target.description,
                enabled=target.enabled,
                headline=headline,
                monitor_count=len(monitor_summaries),
                healthy_monitors=sum(item.headline == "healthy" for item in monitor_summaries),
                degraded_monitors=sum(item.headline == "degraded" for item in monitor_summaries),
                unhealthy_monitors=sum(item.headline == "unhealthy" for item in monitor_summaries),
                unknown_monitors=sum(
                    item.headline in {"unknown", "disabled"} for item in monitor_summaries
                ),
                agent_count=len(agent_ids),
                monitors=monitor_summaries,
            )
        )
    return summaries


async def query_dashboard_overview(*, realm_id: UUID, settings: Settings) -> DashboardOverview:
    targets = await query_target_summaries(realm_id=realm_id, settings=settings)
    agent_count = await Agent.filter(realm_id=realm_id, archived_at=None).count()
    return DashboardOverview(
        target_count=len(targets),
        monitor_count=sum(target.monitor_count for target in targets),
        agent_count=agent_count,
        healthy_targets=sum(target.headline == "healthy" for target in targets),
        degraded_targets=sum(target.headline == "degraded" for target in targets),
        unhealthy_targets=sum(target.headline == "unhealthy" for target in targets),
        unknown_targets=sum(target.headline in {"unknown", "disabled"} for target in targets),
        targets=targets,
    )
