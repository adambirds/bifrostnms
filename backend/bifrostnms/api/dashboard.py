from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from bifrostnms.auth.permissions import require_realm_permission
from bifrostnms.auth.roles import RealmPermission
from bifrostnms.config import get_settings
from bifrostnms.models import Monitor, Target
from bifrostnms.monitoring.dashboard import (
    query_monitor_states,
    query_probe_history,
    query_recent_observations,
)
from bifrostnms.monitoring.target_dashboard import (
    query_dashboard_overview,
    query_target_summaries,
)
from bifrostnms.schemas.dashboard import (
    DashboardOverview,
    MonitorStateSummary,
    ObservationSummary,
    ProbeHistoryPoint,
    TargetOperationalSummary,
)

router = APIRouter(prefix="/monitoring/dashboard", tags=["monitoring-dashboard"])


def _history_range(*, start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    resolved_end = end or datetime.now(UTC)
    resolved_start = start or resolved_end - timedelta(hours=24)
    if (
        resolved_start.tzinfo is None
        or resolved_end.tzinfo is None
        or resolved_start >= resolved_end
        or resolved_end - resolved_start > timedelta(days=30)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="History range must be positive and no longer than 30 days",
        )
    return resolved_start, resolved_end


@router.get("/overview", response_model=DashboardOverview)
async def overview(request: Request) -> DashboardOverview:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    return await query_dashboard_overview(
        realm_id=authorization.realm.id,
        settings=get_settings(),
    )


@router.get("/targets", response_model=list[TargetOperationalSummary])
async def target_summaries(request: Request) -> list[TargetOperationalSummary]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    return await query_target_summaries(
        realm_id=authorization.realm.id,
        settings=get_settings(),
    )


@router.get("/targets/{target_id}", response_model=TargetOperationalSummary)
async def target_summary(target_id: UUID, request: Request) -> TargetOperationalSummary:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    target = await Target.filter(
        id=target_id,
        realm=authorization.realm,
        archived_at=None,
    ).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    summaries = await query_target_summaries(
        realm_id=authorization.realm.id,
        settings=get_settings(),
    )
    for summary in summaries:
        if summary.target_id == target_id:
            return summary
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")


@router.get("/current-state", response_model=list[MonitorStateSummary])
async def current_state(request: Request) -> list[MonitorStateSummary]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    return await query_monitor_states(
        realm_id=authorization.realm.id,
        settings=get_settings(),
    )


@router.get("/recent-observations", response_model=list[ObservationSummary])
async def recent_observations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=250),
) -> list[ObservationSummary]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    return await query_recent_observations(realm_id=authorization.realm.id, limit=limit)


@router.get(
    "/monitors/{monitor_id}/history",
    response_model=list[ProbeHistoryPoint],
)
async def monitor_history(
    monitor_id: UUID,
    request: Request,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=5000, ge=1, le=5000),
) -> list[ProbeHistoryPoint]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    monitor = await Monitor.filter(
        id=monitor_id,
        realm=authorization.realm,
        archived_at=None,
    ).first()
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    resolved_start, resolved_end = _history_range(start=start, end=end)
    return await query_probe_history(
        realm_id=authorization.realm.id,
        monitor_id=monitor.id,
        probe_type=monitor.probe_type,
        start=resolved_start,
        end=resolved_end,
        limit=limit,
    )
