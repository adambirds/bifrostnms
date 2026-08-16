from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from bifrostnms.models import ProbeType


class MonitoringResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    realm_id: UUID
    created_at: datetime
    updated_at: datetime


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    enabled: bool = True


class AgentResponse(MonitoringResponse):
    name: str
    description: str | None
    enabled: bool
    archived_at: datetime | None


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    address: str = Field(min_length=1, max_length=253)
    enabled: bool = True


class TargetResponse(MonitoringResponse):
    name: str
    description: str | None
    address: str
    enabled: bool
    archived_at: datetime | None


class MonitorCreate(BaseModel):
    target_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    probe_type: ProbeType
    interval_seconds: int = Field(ge=1)
    timeout_seconds: int = Field(ge=1)
    configuration: dict[str, Any] = Field(default_factory=dict)


class MonitorResponse(MonitoringResponse):
    target_id: UUID
    name: str
    description: str | None
    probe_type: ProbeType
    interval_seconds: int
    timeout_seconds: int
    configuration: dict[str, Any]
    enabled: bool
    revision: int
    archived_at: datetime | None
