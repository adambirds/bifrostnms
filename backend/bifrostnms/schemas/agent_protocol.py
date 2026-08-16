from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AgentCapabilities(BaseModel):
    probes: dict[str, int] = Field(default_factory=dict)
    runtime_flags: list[str] = Field(default_factory=list)
    external_tools: list[str] = Field(default_factory=list)


class AgentEnrolmentRequest(BaseModel):
    protocol_version: Literal[1]
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
