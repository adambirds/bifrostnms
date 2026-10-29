from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from bifrostnms.auth.permissions import require_realm_permission
from bifrostnms.auth.roles import RealmPermission
from bifrostnms.monitoring.bulk import create_monitors_bulk
from bifrostnms.monitoring.domain import MonitoringDomainError, ResourceStateError
from bifrostnms.schemas.monitoring_api import (
    BulkMonitorCreate,
    BulkMonitorCreateResponse,
    BulkMonitorSkippedTarget,
    MonitorResponse,
)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.post(
    "/monitors/bulk",
    response_model=BulkMonitorCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bulk_monitors(
    payload: BulkMonitorCreate,
    request: Request,
) -> BulkMonitorCreateResponse:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    try:
        created, skipped = await create_monitors_bulk(
            realm=authorization.realm,
            payload=payload,
        )
    except (MonitoringDomainError, ResourceStateError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return BulkMonitorCreateResponse(
        created=[MonitorResponse.model_validate(monitor) for monitor in created],
        skipped=[
            BulkMonitorSkippedTarget(
                target_id=item.target_id,
                target_name=item.target_name,
                reason=item.reason,
            )
            for item in skipped
        ],
    )
