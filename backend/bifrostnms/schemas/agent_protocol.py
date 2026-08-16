from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

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
