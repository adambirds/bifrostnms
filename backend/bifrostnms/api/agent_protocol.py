from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from bifrostnms.agents import (
    AgentAuthentication,
    AgentProtocolError,
    EnrolmentError,
    acknowledge_configuration,
    authenticate_agent,
    exchange_enrolment_token,
    get_or_create_configuration,
    ingest_observations,
    record_heartbeat,
    require_supported_protocol,
)
from bifrostnms.auth.audit import AuditActorType, AuditOutcome, record_audit_event
from bifrostnms.config import get_settings
from bifrostnms.schemas.agent_protocol import (
    AgentConfigurationAcknowledgement,
    AgentConfigurationAcknowledgementResponse,
    AgentConfigurationResponse,
    AgentEnrolmentRequest,
    AgentEnrolmentResponse,
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    AgentObservationUpload,
    AgentObservationUploadResponse,
)

router = APIRouter(prefix="/agent", tags=["agent protocol"])
MAXIMUM_OBSERVATION_UPLOAD_BYTES = 1 << 20


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
        actor_type=AuditActorType.ANONYMOUS,
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
        desired_configuration_hash=(
            f"sha256:{configuration.desired_content_hash}"
            if configuration.desired_content_hash
            else ""
        ),
        configuration_update_available=(
            configuration.desired_revision != payload.active_configuration_revision
        ),
    )


@router.get(
    "/config",
    response_model=AgentConfigurationResponse,
    responses={304: {"description": "The active configuration is current."}},
)
async def get_configuration(
    authentication: Annotated[AgentAuthentication, Depends(authenticate_agent)],
    protocol_version: Annotated[int, Query(ge=1)] = 1,
    active_revision: Annotated[int | None, Query(ge=0)] = None,
    content_hash: str | None = None,
) -> AgentConfigurationResponse | Response:
    require_supported_protocol(protocol_version)
    result = await get_or_create_configuration(authentication)
    response_hash = f"sha256:{result.snapshot.content_hash}"
    if active_revision == result.snapshot.revision and content_hash == response_hash:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)
    return AgentConfigurationResponse(
        agent_id=authentication.agent.id,
        realm_id=authentication.realm.id,
        revision=result.snapshot.revision,
        content_hash=response_hash,
        generated_at=result.snapshot.created_at,
        monitors=result.content["monitors"],
    )


@router.post(
    "/config/acknowledge",
    response_model=AgentConfigurationAcknowledgementResponse,
)
async def acknowledge_agent_configuration(
    payload: AgentConfigurationAcknowledgement,
    authentication: Annotated[AgentAuthentication, Depends(authenticate_agent)],
) -> AgentConfigurationAcknowledgementResponse:
    require_supported_protocol(payload.protocol_version)
    state = await acknowledge_configuration(
        authentication=authentication,
        revision=payload.revision,
        content_hash=payload.content_hash,
        activated_at=payload.activated_at,
    )
    return AgentConfigurationAcknowledgementResponse(
        acknowledged_revision=state.acknowledged_revision,
        acknowledged_content_hash=f"sha256:{state.acknowledged_content_hash}",
    )


@router.post("/observations", response_model=AgentObservationUploadResponse)
async def upload_observations(
    payload: AgentObservationUpload,
    request: Request,
    authentication: Annotated[AgentAuthentication, Depends(authenticate_agent)],
) -> AgentObservationUploadResponse:
    content_length = request.headers.get("content-length")
    try:
        exceeds_limit = (
            content_length is not None and int(content_length) > MAXIMUM_OBSERVATION_UPLOAD_BYTES
        )
    except ValueError:
        exceeds_limit = True
    if exceeds_limit:
        raise AgentProtocolError(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="observation_batch_too_large",
            message="The serialized observation batch exceeds 1 MiB.",
            retryable=True,
        )
    require_supported_protocol(payload.protocol_version)
    if payload.result_schema_version != 1:
        raise AgentProtocolError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="unsupported_result_schema",
            message="The observation result schema version is unsupported.",
            retryable=False,
        )
    results = await ingest_observations(authentication=authentication, upload=payload)
    return AgentObservationUploadResponse(batch_id=payload.batch_id, results=results)
