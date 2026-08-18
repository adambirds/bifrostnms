from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class BulkMonitorCreate(BaseModel):
    target_ids: list[UUID] = Field(default_factory=list, max_length=500)
    target_group_id: UUID | None = None
    source_monitor_id: UUID | None = None
    name_template: str = Field(default="{target} - {probe}", min_length=1, max_length=200)
    description: str | None = None
    probe_type: ProbeType | None = None
    interval_seconds: int | None = Field(default=None, ge=1)
    timeout_seconds: int | None = Field(default=None, ge=1)
    configuration: dict[str, Any] | None = None
    agent_ids: list[UUID] = Field(default_factory=list, max_length=500)
    agent_group_ids: list[UUID] = Field(default_factory=list, max_length=500)
    skip_existing: bool = True

    @model_validator(mode="after")
    def validate_selection_and_definition(self) -> Self:
        if not self.target_ids and self.target_group_id is None:
            raise ValueError("At least one target or a target group is required")
        if len(self.target_ids) != len(set(self.target_ids)):
            raise ValueError("target_ids must be unique")
        if len(self.agent_ids) != len(set(self.agent_ids)):
            raise ValueError("agent_ids must be unique")
        if len(self.agent_group_ids) != len(set(self.agent_group_ids)):
            raise ValueError("agent_group_ids must be unique")
        if self.source_monitor_id is None and (
            self.probe_type is None
            or self.interval_seconds is None
            or self.timeout_seconds is None
            or self.configuration is None
        ):
            raise ValueError(
                "probe_type, interval_seconds, timeout_seconds and configuration "
                "are required when source_monitor_id is not supplied"
            )
        return self


class BulkMonitorSkippedTarget(BaseModel):
    target_id: UUID
    target_name: str
    reason: str


class BulkMonitorCreateResponse(BaseModel):
    created: list[MonitorResponse]
    skipped: list[BulkMonitorSkippedTarget]


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
