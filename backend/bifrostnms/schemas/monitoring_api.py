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


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    parent_id: UUID | None = None


class AgentGroupCreate(GroupCreate):
    enabled: bool = True


class AgentGroupResponse(MonitoringResponse):
    parent_id: UUID | None
    name: str
    description: str | None
    enabled: bool
    archived_at: datetime | None


class TargetGroupResponse(MonitoringResponse):
    parent_id: UUID | None
    name: str
    description: str | None
    archived_at: datetime | None


class AgentGroupMembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    realm_id: UUID
    agent_group_id: UUID
    agent_id: UUID
    created_at: datetime


class TargetGroupMembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    realm_id: UUID
    target_group_id: UUID
    target_id: UUID
    created_at: datetime


class MonitorAgentAssignmentResponse(MonitoringResponse):
    monitor_id: UUID
    agent_id: UUID
    enabled: bool


class MonitorAgentGroupAssignmentResponse(MonitoringResponse):
    monitor_id: UUID
    agent_group_id: UUID
    enabled: bool


class IcmpHistoryPoint(BaseModel):
    scheduled_at: datetime
    agent_id: UUID
    assessment: str
    packets_sent: int
    packets_received: int
    packet_loss_percent: float
    min_rtt_ms: float | None
    avg_rtt_ms: float | None
    median_rtt_ms: float | None
    max_rtt_ms: float | None
    p95_rtt_ms: float | None
    jitter_ms: float | None
    rtt_samples_ms: list[float]
