from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from tortoise.exceptions import IntegrityError

from bifrostnms.auth.permissions import require_realm_permission
from bifrostnms.auth.roles import RealmPermission
from bifrostnms.models import Agent, Monitor, Target
from bifrostnms.monitoring import ResourceStateError, archive_target, create_monitor
from bifrostnms.monitoring.domain import MonitoringDomainError
from bifrostnms.schemas.monitoring_api import (
    AgentCreate,
    AgentResponse,
    MonitorCreate,
    MonitorResponse,
    TargetCreate,
    TargetResponse,
)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(request: Request) -> list[AgentResponse]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    agents = await Agent.filter(realm=authorization.realm, archived_at=None).order_by("name")
    return [AgentResponse.model_validate(agent) for agent in agents]


@router.post("/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreate, request: Request) -> AgentResponse:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    try:
        agent = await Agent.create(
            realm=authorization.realm,
            name=payload.name.strip(),
            description=payload.description,
            enabled=payload.enabled,
        )
    except IntegrityError as exc:
        raise _conflict("An agent with that name already exists") from exc
    return AgentResponse.model_validate(agent)


@router.get("/targets", response_model=list[TargetResponse])
async def list_targets(request: Request) -> list[TargetResponse]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    targets = await Target.filter(realm=authorization.realm, archived_at=None).order_by("name")
    return [TargetResponse.model_validate(target) for target in targets]


@router.post("/targets", response_model=TargetResponse, status_code=status.HTTP_201_CREATED)
async def create_target(payload: TargetCreate, request: Request) -> TargetResponse:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    try:
        target = await Target.create(
            realm=authorization.realm,
            name=payload.name.strip(),
            description=payload.description,
            address=payload.address.strip(),
            enabled=payload.enabled,
        )
    except IntegrityError as exc:
        raise _conflict("A target with that name already exists") from exc
    return TargetResponse.model_validate(target)


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(target_id: UUID, request: Request) -> None:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    target = await Target.filter(id=target_id, realm=authorization.realm).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    await archive_target(realm=authorization.realm, target=target)


@router.get("/monitors", response_model=list[MonitorResponse])
async def list_monitors(request: Request) -> list[MonitorResponse]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    monitors = await Monitor.filter(realm=authorization.realm, archived_at=None).order_by("name")
    return [MonitorResponse.model_validate(monitor) for monitor in monitors]


@router.post("/monitors", response_model=MonitorResponse, status_code=status.HTTP_201_CREATED)
async def create_monitor_endpoint(payload: MonitorCreate, request: Request) -> MonitorResponse:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    target = await Target.filter(id=payload.target_id, realm=authorization.realm).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    try:
        monitor = await create_monitor(
            realm=authorization.realm,
            target=target,
            name=payload.name.strip(),
            description=payload.description,
            probe_type=payload.probe_type,
            interval_seconds=payload.interval_seconds,
            timeout_seconds=payload.timeout_seconds,
            configuration=payload.configuration,
        )
    except IntegrityError as exc:
        raise _conflict("A monitor with that name already exists") from exc
    except (MonitoringDomainError, ResourceStateError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return MonitorResponse.model_validate(monitor)
