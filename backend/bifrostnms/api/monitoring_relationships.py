from fastapi import APIRouter, Request

from bifrostnms.auth.permissions import require_realm_permission
from bifrostnms.auth.roles import RealmPermission
from bifrostnms.models import (
    AgentGroupMembership,
    MonitorAgentAssignment,
    MonitorAgentGroupAssignment,
    TargetGroupMembership,
)
from bifrostnms.schemas.monitoring_api import (
    AgentGroupMembershipResponse,
    MonitorAgentAssignmentResponse,
    MonitorAgentGroupAssignmentResponse,
    TargetGroupMembershipResponse,
)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get(
    "/agent-group-memberships",
    response_model=list[AgentGroupMembershipResponse],
)
async def list_agent_group_memberships(request: Request) -> list[AgentGroupMembershipResponse]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    memberships = await AgentGroupMembership.filter(realm=authorization.realm).order_by(
        "agent_group_id", "agent_id"
    )
    return [AgentGroupMembershipResponse.model_validate(item) for item in memberships]


@router.get(
    "/target-group-memberships",
    response_model=list[TargetGroupMembershipResponse],
)
async def list_target_group_memberships(request: Request) -> list[TargetGroupMembershipResponse]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    memberships = await TargetGroupMembership.filter(realm=authorization.realm).order_by(
        "target_group_id", "target_id"
    )
    return [TargetGroupMembershipResponse.model_validate(item) for item in memberships]


@router.get(
    "/monitor-agent-assignments",
    response_model=list[MonitorAgentAssignmentResponse],
)
async def list_monitor_agent_assignments(request: Request) -> list[MonitorAgentAssignmentResponse]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    assignments = await MonitorAgentAssignment.filter(realm=authorization.realm).order_by(
        "monitor_id", "agent_id"
    )
    return [MonitorAgentAssignmentResponse.model_validate(item) for item in assignments]


@router.get(
    "/monitor-agent-group-assignments",
    response_model=list[MonitorAgentGroupAssignmentResponse],
)
async def list_monitor_agent_group_assignments(
    request: Request,
) -> list[MonitorAgentGroupAssignmentResponse]:
    authorization = await require_realm_permission(request, RealmPermission.MONITORING_READ)
    assignments = await MonitorAgentGroupAssignment.filter(realm=authorization.realm).order_by(
        "monitor_id", "agent_group_id"
    )
    return [MonitorAgentGroupAssignmentResponse.model_validate(item) for item in assignments]
