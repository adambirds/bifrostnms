from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from tortoise.exceptions import IntegrityError

from bifrostnms.auth.permissions import require_realm_permission
from bifrostnms.auth.roles import RealmPermission
from bifrostnms.models import Monitor, Target
from bifrostnms.monitoring import ResourceStateError, update_monitor_behavior
from bifrostnms.monitoring.domain import MonitoringDomainError
from bifrostnms.schemas.monitor_management import MonitorUpdate
from bifrostnms.schemas.monitoring_api import MonitorResponse

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/monitors/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(monitor_id: UUID, request: Request) -> MonitorResponse:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    monitor = await Monitor.filter(
        id=monitor_id,
        realm=authorization.realm,
        archived_at=None,
    ).first()
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return MonitorResponse.model_validate(monitor)


@router.put("/monitors/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: UUID,
    payload: MonitorUpdate,
    request: Request,
) -> MonitorResponse:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    monitor = await Monitor.filter(
        id=monitor_id,
        realm=authorization.realm,
        archived_at=None,
    ).first()
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")

    target = await Target.filter(
        id=payload.target_id,
        realm=authorization.realm,
        archived_at=None,
    ).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    name = payload.name.strip()
    description = payload.description.strip() if payload.description else None
    if await Monitor.filter(realm=authorization.realm, name=name).exclude(id=monitor.id).exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A monitor with that name already exists",
        )

    try:
        monitor = await update_monitor_behavior(
            monitor,
            realm=authorization.realm,
            target=target,
            probe_type=payload.probe_type,
            interval_seconds=payload.interval_seconds,
            timeout_seconds=payload.timeout_seconds,
            configuration=payload.configuration,
        )
        if monitor.name != name or monitor.description != description:
            await Monitor.filter(id=monitor.id, realm=authorization.realm).update(
                name=name,
                description=description,
                updated_at=datetime.now(UTC),
            )
            await monitor.refresh_from_db()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A monitor with that name already exists",
        ) from exc
    except (MonitoringDomainError, ResourceStateError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return MonitorResponse.model_validate(monitor)
