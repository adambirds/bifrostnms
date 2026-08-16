from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from tortoise.exceptions import IntegrityError

from bifrostnms.agents import issue_enrolment_token, revoke_credential, revoke_enrolment_token
from bifrostnms.auth.audit import AuditActorType, AuditOutcome, record_audit_event
from bifrostnms.auth.permissions import require_realm_permission
from bifrostnms.auth.roles import RealmPermission
from bifrostnms.config import get_settings
from bifrostnms.models import (
    Agent,
    AgentCredential,
    AgentGroup,
    AgentOperationalState,
    Monitor,
    Target,
    TargetGroup,
    TargetGroupMembership,
)
from bifrostnms.monitoring import (
    ResourceStateError,
    add_agent_to_group,
    add_target_to_group,
    archive_target,
    assign_monitor_to_agent,
    assign_monitor_to_agent_group,
    create_monitor,
    remove_agent_from_group,
    unassign_monitor_from_agent,
    unassign_monitor_from_agent_group,
)
from bifrostnms.monitoring.domain import MonitoringDomainError
from bifrostnms.schemas.agent_protocol import (
    AgentCredentialResponse,
    AgentStatusResponse,
    DatabaseHealth,
    EnrolmentTokenResponse,
    SchedulerState,
)
from bifrostnms.schemas.monitoring_api import (
    AgentCreate,
    AgentGroupCreate,
    AgentGroupMembershipResponse,
    AgentGroupResponse,
    AgentResponse,
    GroupCreate,
    MonitorAgentAssignmentResponse,
    MonitorAgentGroupAssignmentResponse,
    MonitorCreate,
    MonitorResponse,
    TargetCreate,
    TargetGroupMembershipResponse,
    TargetGroupResponse,
    TargetResponse,
)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _unprocessable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


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


@router.post(
    "/agents/{agent_id}/enrolment-tokens",
    response_model=EnrolmentTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_enrolment_token(agent_id: UUID, request: Request) -> EnrolmentTokenResponse:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    agent = await Agent.filter(
        id=agent_id,
        realm=authorization.realm,
        enabled=True,
        archived_at=None,
    ).first()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    token, raw_token = await issue_enrolment_token(realm=authorization.realm, agent=agent)
    await record_audit_event(
        action="agent.enrolment.create",
        outcome=AuditOutcome.SUCCESS,
        actor_type=AuditActorType.USER,
        request=request,
        realm=authorization.realm,
        actor_user=authorization.user,
        target_type="agent_enrolment_token",
        target_id=str(token.id),
        superuser_bypass=authorization.is_superuser_bypass,
    )
    return EnrolmentTokenResponse(
        id=token.id,
        agent_id=agent.id,
        enrolment_token=raw_token,
        expires_at=token.expires_at,
    )


@router.delete("/agents/{agent_id}/enrolment-tokens/{token_id}", status_code=204)
async def delete_agent_enrolment_token(agent_id: UUID, token_id: UUID, request: Request) -> None:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    agent = await Agent.filter(id=agent_id, realm=authorization.realm).first()
    if agent is None or not await revoke_enrolment_token(
        realm=authorization.realm, agent=agent, token_id=token_id
    ):
        raise HTTPException(status_code=404, detail="Enrolment token not found")
    await record_audit_event(
        action="agent.enrolment.revoke",
        outcome=AuditOutcome.SUCCESS,
        actor_type=AuditActorType.USER,
        request=request,
        realm=authorization.realm,
        actor_user=authorization.user,
        target_type="agent_enrolment_token",
        target_id=str(token_id),
        superuser_bypass=authorization.is_superuser_bypass,
    )


@router.get("/agents/{agent_id}/credentials", response_model=list[AgentCredentialResponse])
async def list_agent_credentials(agent_id: UUID, request: Request) -> list[AgentCredentialResponse]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    if not await Agent.filter(id=agent_id, realm=authorization.realm).exists():
        raise HTTPException(status_code=404, detail="Agent not found")
    credentials = await AgentCredential.filter(
        agent_id=agent_id, realm=authorization.realm
    ).order_by("created_at")
    return [
        AgentCredentialResponse.model_validate(item, from_attributes=True) for item in credentials
    ]


@router.get("/agents/{agent_id}/status", response_model=AgentStatusResponse)
async def get_agent_status(agent_id: UUID, request: Request) -> AgentStatusResponse:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    agent = await Agent.filter(id=agent_id, realm=authorization.realm).first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    state = await AgentOperationalState.filter(agent=agent, realm=authorization.realm).first()
    if state is None:
        return AgentStatusResponse(
            agent_id=agent.id,
            online=False,
            last_heartbeat_at=None,
            agent_version=None,
            platform=None,
            architecture=None,
            hostname=None,
            capabilities={},
            active_configuration_revision=0,
            known_desired_configuration_revision=0,
            queue_depth=0,
            queue_bytes=0,
            oldest_pending_observation_at=None,
            database_health=None,
            scheduler_state=None,
            clock_offset_ms=None,
            warnings=[],
        )
    online_cutoff = datetime.now(UTC) - timedelta(
        seconds=get_settings().agent_offline_after_seconds
    )
    return AgentStatusResponse(
        agent_id=agent.id,
        online=(
            agent.enabled and agent.archived_at is None and state.last_heartbeat_at >= online_cutoff
        ),
        last_heartbeat_at=state.last_heartbeat_at,
        agent_version=state.agent_version,
        platform=state.platform,
        architecture=state.architecture,
        hostname=state.hostname,
        capabilities=state.capabilities,
        active_configuration_revision=state.active_configuration_revision,
        known_desired_configuration_revision=(state.known_desired_configuration_revision),
        queue_depth=state.queue_depth,
        queue_bytes=state.queue_bytes,
        oldest_pending_observation_at=state.oldest_pending_observation_at,
        database_health=DatabaseHealth(state.database_health),
        scheduler_state=SchedulerState(state.scheduler_state),
        clock_offset_ms=state.clock_offset_ms,
        warnings=state.warnings,
    )


@router.delete("/agents/{agent_id}/credentials/{credential_id}", status_code=204)
async def delete_agent_credential(agent_id: UUID, credential_id: UUID, request: Request) -> None:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    credential = await AgentCredential.filter(
        id=credential_id, agent_id=agent_id, realm=authorization.realm
    ).first()
    if credential is None or not await revoke_credential(
        realm=authorization.realm, credential_id=credential.id
    ):
        raise HTTPException(status_code=404, detail="Agent credential not found")
    await record_audit_event(
        action="agent.credential.revoke",
        outcome=AuditOutcome.SUCCESS,
        actor_type=AuditActorType.USER,
        request=request,
        realm=authorization.realm,
        actor_user=authorization.user,
        target_type="agent_credential",
        target_id=str(credential.id),
        superuser_bypass=authorization.is_superuser_bypass,
    )


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


@router.get("/agent-groups", response_model=list[AgentGroupResponse])
async def list_agent_groups(request: Request) -> list[AgentGroupResponse]:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    groups = await AgentGroup.filter(realm=auth.realm, archived_at=None).order_by("name")
    return [AgentGroupResponse.model_validate(group) for group in groups]


@router.post("/agent-groups", response_model=AgentGroupResponse, status_code=201)
async def create_agent_group(payload: AgentGroupCreate, request: Request) -> AgentGroupResponse:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    parent = None
    if payload.parent_id is not None:
        parent = await AgentGroup.filter(
            id=payload.parent_id, realm=auth.realm, archived_at=None
        ).first()
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent not found")
    try:
        group = await AgentGroup.create(
            realm=auth.realm,
            parent=parent,
            name=payload.name.strip(),
            description=payload.description,
            enabled=payload.enabled,
        )
    except IntegrityError as exc:
        raise _conflict("An agent group with that sibling name already exists") from exc
    return AgentGroupResponse.model_validate(group)


@router.get("/target-groups", response_model=list[TargetGroupResponse])
async def list_target_groups(request: Request) -> list[TargetGroupResponse]:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    groups = await TargetGroup.filter(realm=auth.realm, archived_at=None).order_by("name")
    return [TargetGroupResponse.model_validate(group) for group in groups]


@router.post("/target-groups", response_model=TargetGroupResponse, status_code=201)
async def create_target_group(payload: GroupCreate, request: Request) -> TargetGroupResponse:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    parent = None
    if payload.parent_id is not None:
        parent = await TargetGroup.filter(
            id=payload.parent_id, realm=auth.realm, archived_at=None
        ).first()
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent not found")
    try:
        group = await TargetGroup.create(
            realm=auth.realm,
            parent=parent,
            name=payload.name.strip(),
            description=payload.description,
        )
    except IntegrityError as exc:
        raise _conflict("A target group with that sibling name already exists") from exc
    return TargetGroupResponse.model_validate(group)


@router.put(
    "/agent-groups/{group_id}/agents/{agent_id}",
    response_model=AgentGroupMembershipResponse,
)
async def create_agent_group_membership(
    group_id: UUID, agent_id: UUID, request: Request
) -> AgentGroupMembershipResponse:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    group = await AgentGroup.filter(id=group_id, realm=auth.realm).first()
    agent = await Agent.filter(id=agent_id, realm=auth.realm).first()
    if group is None or agent is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        membership = await add_agent_to_group(realm=auth.realm, group=group, agent=agent)
    except MonitoringDomainError as exc:
        raise _unprocessable(exc) from exc
    return AgentGroupMembershipResponse.model_validate(membership)


@router.delete("/agent-groups/{group_id}/agents/{agent_id}", status_code=204)
async def delete_agent_group_membership(group_id: UUID, agent_id: UUID, request: Request) -> None:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    group = await AgentGroup.filter(id=group_id, realm=auth.realm).first()
    agent = await Agent.filter(id=agent_id, realm=auth.realm).first()
    if group is None or agent is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not await remove_agent_from_group(realm=auth.realm, group=group, agent=agent):
        raise HTTPException(status_code=404, detail="Membership not found")


@router.put(
    "/target-groups/{group_id}/targets/{target_id}",
    response_model=TargetGroupMembershipResponse,
)
async def create_target_group_membership(
    group_id: UUID, target_id: UUID, request: Request
) -> TargetGroupMembershipResponse:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    group = await TargetGroup.filter(id=group_id, realm=auth.realm).first()
    target = await Target.filter(id=target_id, realm=auth.realm).first()
    if group is None or target is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        membership = await add_target_to_group(realm=auth.realm, group=group, target=target)
    except MonitoringDomainError as exc:
        raise _unprocessable(exc) from exc
    return TargetGroupMembershipResponse.model_validate(membership)


@router.delete("/target-groups/{group_id}/targets/{target_id}", status_code=204)
async def delete_target_group_membership(group_id: UUID, target_id: UUID, request: Request) -> None:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    deleted = await TargetGroupMembership.filter(
        realm=auth.realm, target_group_id=group_id, target_id=target_id
    ).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail="Membership not found")


@router.put(
    "/monitors/{monitor_id}/agents/{agent_id}",
    response_model=MonitorAgentAssignmentResponse,
)
async def create_monitor_agent_assignment(
    monitor_id: UUID, agent_id: UUID, request: Request
) -> MonitorAgentAssignmentResponse:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    monitor = await Monitor.filter(id=monitor_id, realm=auth.realm).first()
    agent = await Agent.filter(id=agent_id, realm=auth.realm).first()
    if monitor is None or agent is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        assignment = await assign_monitor_to_agent(realm=auth.realm, monitor=monitor, agent=agent)
    except MonitoringDomainError as exc:
        raise _unprocessable(exc) from exc
    return MonitorAgentAssignmentResponse.model_validate(assignment)


@router.delete("/monitors/{monitor_id}/agents/{agent_id}", status_code=204)
async def delete_monitor_agent_assignment(
    monitor_id: UUID, agent_id: UUID, request: Request
) -> None:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    monitor = await Monitor.filter(id=monitor_id, realm=auth.realm).first()
    agent = await Agent.filter(id=agent_id, realm=auth.realm).first()
    if monitor is None or agent is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not await unassign_monitor_from_agent(realm=auth.realm, monitor=monitor, agent=agent):
        raise HTTPException(status_code=404, detail="Assignment not found")


@router.put(
    "/monitors/{monitor_id}/agent-groups/{group_id}",
    response_model=MonitorAgentGroupAssignmentResponse,
)
async def create_monitor_agent_group_assignment(
    monitor_id: UUID, group_id: UUID, request: Request
) -> MonitorAgentGroupAssignmentResponse:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    monitor = await Monitor.filter(id=monitor_id, realm=auth.realm).first()
    group = await AgentGroup.filter(id=group_id, realm=auth.realm).first()
    if monitor is None or group is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        assignment = await assign_monitor_to_agent_group(
            realm=auth.realm, monitor=monitor, group=group
        )
    except MonitoringDomainError as exc:
        raise _unprocessable(exc) from exc
    return MonitorAgentGroupAssignmentResponse.model_validate(assignment)


@router.delete("/monitors/{monitor_id}/agent-groups/{group_id}", status_code=204)
async def delete_monitor_agent_group_assignment(
    monitor_id: UUID, group_id: UUID, request: Request
) -> None:
    auth = await require_realm_permission(request, RealmPermission.MONITORING_MANAGE)
    monitor = await Monitor.filter(id=monitor_id, realm=auth.realm).first()
    group = await AgentGroup.filter(id=group_id, realm=auth.realm).first()
    if monitor is None or group is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not await unassign_monitor_from_agent_group(realm=auth.realm, monitor=monitor, group=group):
        raise HTTPException(status_code=404, detail="Assignment not found")
