from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

BoundedWarning = Annotated[str, StringConstraints(max_length=500)]


class ProbeCapability(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_versions: list[int] = Field(default_factory=list, max_length=20)
    available: bool


class AgentCapabilities(BaseModel):
    model_config = ConfigDict(extra="allow")

    probes: dict[str, ProbeCapability] = Field(default_factory=dict, max_length=50)
    runtime: dict[str, bool] = Field(default_factory=dict, max_length=50)
    external_tools: dict[str, str] = Field(default_factory=dict, max_length=50)


class AgentEnrolmentRequest(BaseModel):
    protocol_version: int = Field(ge=1)
    enrolment_token: str = Field(min_length=32)
    agent_version: str = Field(min_length=1, max_length=120)
    platform: str = Field(min_length=1, max_length=120)
    architecture: str = Field(min_length=1, max_length=120)
    hostname: str = Field(min_length=1, max_length=253)
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)


class AgentEnrolmentResponse(BaseModel):
    protocol_version: Literal[1] = 1
    realm_id: UUID
    agent_id: UUID
    credential_id: UUID
    credential: str
    server_time: datetime
    heartbeat_interval_seconds: int
    configuration_poll_interval_seconds: int


class EnrolmentTokenResponse(BaseModel):
    id: UUID
    agent_id: UUID
    enrolment_token: str
    expires_at: datetime


class AgentCredentialResponse(BaseModel):
    id: UUID
    agent_id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class DatabaseHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class SchedulerState(StrEnum):
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"


class AgentHeartbeatRequest(BaseModel):
    protocol_version: int = Field(ge=1)
    agent_version: str = Field(min_length=1, max_length=120)
    platform: str = Field(min_length=1, max_length=120)
    architecture: str = Field(min_length=1, max_length=120)
    hostname: str = Field(min_length=1, max_length=253)
    capabilities: AgentCapabilities
    active_configuration_revision: int = Field(ge=0)
    known_desired_configuration_revision: int = Field(ge=0)
    queue_depth: int = Field(ge=0)
    queue_bytes: int = Field(ge=0)
    oldest_pending_observation_at: AwareDatetime | None = None
    database_health: DatabaseHealth
    scheduler_state: SchedulerState
    agent_time: AwareDatetime
    warnings: list[BoundedWarning] = Field(default_factory=list, max_length=20)


class AgentHeartbeatResponse(BaseModel):
    protocol_version: Literal[1] = 1
    minimum_protocol_version: Literal[1] = 1
    maximum_protocol_version: Literal[1] = 1
    server_time: datetime
    heartbeat_interval_seconds: int
    configuration_poll_interval_seconds: int
    desired_configuration_revision: int
    desired_configuration_hash: str
    configuration_update_available: bool


class AgentStatusResponse(BaseModel):
    agent_id: UUID
    online: bool
    last_heartbeat_at: datetime | None
    agent_version: str | None
    platform: str | None
    architecture: str | None
    hostname: str | None
    capabilities: dict[str, Any]
    active_configuration_revision: int
    known_desired_configuration_revision: int
    queue_depth: int
    queue_bytes: int
    oldest_pending_observation_at: datetime | None
    database_health: DatabaseHealth | None
    scheduler_state: SchedulerState | None
    clock_offset_ms: int | None
    warnings: list[str]


class AgentProtocolErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any]


class AgentProtocolErrorResponse(BaseModel):
    error: AgentProtocolErrorBody


class AgentMonitorConfiguration(BaseModel):
    monitor_id: UUID
    target_id: UUID
    monitor_revision: int
    target_address: str
    probe_type: str
    probe_schema_version: int
    interval_seconds: int
    timeout_seconds: int
    missed_run_policy: Literal["skip"] = "skip"
    configuration: dict[str, Any]


class AgentConfigurationResponse(BaseModel):
    protocol_version: Literal[1] = 1
    configuration_schema_version: Literal[1] = 1
    agent_id: UUID
    realm_id: UUID
    revision: int
    content_hash: str
    generated_at: datetime
    monitors: list[AgentMonitorConfiguration]


class AgentConfigurationAcknowledgement(BaseModel):
    protocol_version: int = Field(ge=1)
    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    activated_at: AwareDatetime


class AgentConfigurationAcknowledgementResponse(BaseModel):
    protocol_version: Literal[1] = 1
    acknowledged_revision: int
    acknowledged_content_hash: str


class IcmpObservationResult(BaseModel):
    packets_sent: int = Field(ge=1, le=20)
    packets_received: int = Field(ge=0, le=20)
    packet_loss_percent: float = Field(ge=0, le=100)
    min_rtt_ms: float | None = Field(default=None, ge=0)
    avg_rtt_ms: float | None = Field(default=None, ge=0)
    median_rtt_ms: float | None = Field(default=None, ge=0)
    max_rtt_ms: float | None = Field(default=None, ge=0)
    p95_rtt_ms: float | None = Field(default=None, ge=0)
    jitter_ms: float | None = Field(default=None, ge=0)
    rtt_samples_ms: list[Annotated[float, Field(ge=0)]] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_packet_counts(self) -> Self:
        if self.packets_received > self.packets_sent:
            raise ValueError("packets_received cannot exceed packets_sent")
        if len(self.rtt_samples_ms) != self.packets_received:
            raise ValueError("RTT sample count must equal packets_received")
        return self


class HttpObservationResult(BaseModel):
    method: Literal["GET", "HEAD"]
    scheme: Literal["http", "https"]
    status_code: int | None = Field(default=None, ge=100, le=599)
    redirect_count: int = Field(ge=0, le=20)
    response_size_bytes: int | None = Field(default=None, ge=0)
    dns_ms: float | None = Field(default=None, ge=0)
    connect_ms: float | None = Field(default=None, ge=0)
    tls_ms: float | None = Field(default=None, ge=0)
    ttfb_ms: float | None = Field(default=None, ge=0)
    total_ms: float | None = Field(default=None, ge=0)
    assertions_total: int = Field(ge=0, le=100)
    assertions_failed: int = Field(ge=0, le=100)
    final_url_redacted: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def validate_assertion_counts(self) -> Self:
        if self.assertions_failed > self.assertions_total:
            raise ValueError("assertions_failed cannot exceed assertions_total")
        return self


class TcpObservationResult(BaseModel):
    port: int = Field(ge=1, le=65535)
    address_used: str = Field(min_length=2, max_length=45)
    connect_ms: float | None = Field(default=None, ge=0)


class DnsObservationResult(BaseModel):
    resolver_address: str = Field(min_length=2, max_length=45)
    query_name: str = Field(min_length=1, max_length=253)
    query_type: Literal["A", "AAAA", "CNAME", "MX", "NS", "PTR", "SOA", "TXT"]
    response_code: str | None = Field(default=None, max_length=32)
    response_ms: float | None = Field(default=None, ge=0)
    answer_count: int = Field(ge=0, le=1000)
    answers: list[dict[str, Any]] = Field(max_length=1000)
    truncated: bool
    authoritative: bool
    assertions_total: int = Field(ge=0, le=100)
    assertions_failed: int = Field(ge=0, le=100)


class TlsObservationResult(BaseModel):
    port: int = Field(ge=1, le=65535)
    server_name: str = Field(min_length=1, max_length=253)
    protocol_version: str | None = Field(default=None, max_length=32)
    cipher_suite: str | None = Field(default=None, max_length=160)
    handshake_ms: float | None = Field(default=None, ge=0)
    certificate_present: bool
    hostname_valid: bool | None = None
    chain_valid: bool | None = None
    not_before: AwareDatetime | None = None
    not_after: AwareDatetime | None = None
    days_remaining: float | None = None
    subject_name: str | None = Field(default=None, max_length=500)
    issuer_name: str | None = Field(default=None, max_length=500)
    serial_number: str | None = Field(default=None, max_length=160)
    fingerprint_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


ObservationResult = (
    IcmpObservationResult
    | HttpObservationResult
    | TcpObservationResult
    | DnsObservationResult
    | TlsObservationResult
)


class AgentObservation(BaseModel):
    scheduled_at: AwareDatetime
    observation_id: UUID
    monitor_id: UUID
    monitor_revision: int = Field(ge=1)
    probe_type: Literal["icmp", "http", "tcp", "dns", "tls"]
    started_at: AwareDatetime
    finished_at: AwareDatetime
    execution_status: Literal["completed", "failed"]
    assessment: Literal["healthy", "unhealthy", "unknown"]
    error_category: (
        Literal[
            "timeout",
            "resolution",
            "connection",
            "tls",
            "protocol",
            "assertion",
            "permission",
            "invalid_configuration",
            "resource_limit",
            "internal",
        ]
        | None
    ) = None
    error_code: str | None = Field(default=None, max_length=120)
    error_message: str | None = Field(default=None, max_length=500)
    agent_clock_offset_ms: int | None = None
    result: ObservationResult | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.started_at < self.scheduled_at or self.finished_at < self.started_at:
            raise ValueError("observation timestamps are not ordered")
        expected_result_types = {
            "icmp": IcmpObservationResult,
            "http": HttpObservationResult,
            "tcp": TcpObservationResult,
            "dns": DnsObservationResult,
            "tls": TlsObservationResult,
        }
        if self.execution_status == "completed" and not isinstance(
            self.result, expected_result_types[self.probe_type]
        ):
            raise ValueError("completed observation requires the matching typed result")
        if self.execution_status == "failed" and self.result is not None:
            raise ValueError("failed observation cannot include a typed result")
        return self


class AgentObservationUpload(BaseModel):
    protocol_version: int = Field(ge=1)
    result_schema_version: int = Field(ge=1)
    agent_config_revision: int = Field(ge=1)
    batch_id: UUID
    observations: list[AgentObservation] = Field(min_length=1, max_length=500)


class AgentObservationResult(BaseModel):
    scheduled_at: datetime
    observation_id: UUID
    disposition: Literal["accepted", "duplicate", "rejected"]
    code: str | None = None
    retryable: bool = False


class AgentObservationUploadResponse(BaseModel):
    protocol_version: Literal[1] = 1
    batch_id: UUID
    results: list[AgentObservationResult]
    retry_after_seconds: int | None = Field(default=None, ge=1)
