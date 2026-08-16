from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from bifrostnms.agents import (
    AgentAuthentication,
    AgentProtocolError,
    EnrolmentError,
    authenticate_agent,
    exchange_enrolment_token,
    record_heartbeat,
    require_supported_protocol,
)
from bifrostnms.auth.audit import AuditActorType, AuditOutcome, record_audit_event
from bifrostnms.config import get_settings
from bifrostnms.schemas.agent_protocol import (
    AgentEnrolmentRequest,
    AgentEnrolmentResponse,
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
)

router = APIRouter(prefix="/agent", tags=["agent protocol"])


@router.post(
    "/enrol",
    response_model=AgentEnrolmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enrol_agent(payload: AgentEnrolmentRequest, request: Request) -> AgentEnrolmentResponse:
    require_supported_protocol(payload.protocol_version)
    try:
        agent, credential, raw_credential = await exchange_enrolment_token(payload.enrolment_token)
    except EnrolmentError as exc:
        raise AgentProtocolError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_enrolment_token",
            message=str(exc),
            retryable=False,
        ) from exc

    realm = await agent.realm
    await record_audit_event(
        action="agent.enrolment.consume",
        outcome=AuditOutcome.SUCCESS,
        actor_type=AuditActorType.ANONYMOUS,
        request=request,
        realm=realm,
        target_type="agent",
        target_id=str(agent.id),
        metadata={"protocol_version": payload.protocol_version},
    )
    await record_audit_event(
        action="agent.credential.create",
        outcome=AuditOutcome.SUCCESS,
        actor_type=AuditActorType.AGENT,
        request=request,
        realm=realm,
        target_type="agent_credential",
        target_id=str(credential.id),
        metadata={"agent_id": str(agent.id)},
    )
    settings = get_settings()
    return AgentEnrolmentResponse(
        realm_id=agent.realm_id,
        agent_id=agent.id,
        credential_id=credential.id,
        credential=raw_credential,
        server_time=datetime.now(UTC),
        heartbeat_interval_seconds=settings.agent_heartbeat_interval_seconds,
        configuration_poll_interval_seconds=(settings.agent_configuration_poll_interval_seconds),
    )


@router.post("/heartbeat", response_model=AgentHeartbeatResponse)
async def heartbeat(
    payload: AgentHeartbeatRequest,
    authentication: Annotated[AgentAuthentication, Depends(authenticate_agent)],
) -> AgentHeartbeatResponse:
    require_supported_protocol(payload.protocol_version)
    _, configuration = await record_heartbeat(authentication=authentication, payload=payload)
    settings = get_settings()
    return AgentHeartbeatResponse(
        server_time=datetime.now(UTC),
        heartbeat_interval_seconds=settings.agent_heartbeat_interval_seconds,
        configuration_poll_interval_seconds=(settings.agent_configuration_poll_interval_seconds),
        desired_configuration_revision=configuration.desired_revision,
        desired_configuration_hash=configuration.desired_content_hash,
        configuration_update_available=(
            configuration.desired_revision != payload.active_configuration_revision
        ),
    )
