from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from bifrostnms.models import ProbeType

AvailabilityState = Literal[
    "pending_configuration",
    "no_data_yet",
    "healthy",
    "unhealthy",
    "probe_error",
    "overdue",
    "agent_stale",
    "agent_offline",
    "disabled",
]
MonitorHeadline = Literal["healthy", "degraded", "unhealthy", "unknown", "disabled"]


class ObservationSummary(BaseModel):
    observation_id: UUID
    scheduled_at: datetime
    received_at: datetime
    monitor_id: UUID
    agent_id: UUID
    probe_type: ProbeType
    execution_status: Literal["completed", "failed"]
    assessment: Literal["healthy", "unhealthy", "unknown"]
    error_category: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class MonitorAgentState(BaseModel):
    monitor_id: UUID
    monitor_name: str
    agent_id: UUID
    agent_name: str
    probe_type: ProbeType
    availability_state: AvailabilityState
    desired_config_revision: int
    acknowledged_config_revision: int
    last_observation_id: UUID | None = None
    last_scheduled_at: datetime | None = None
    last_received_at: datetime | None = None
    execution_status: Literal["completed", "failed"] | None = None
    assessment: Literal["healthy", "unhealthy", "unknown"] | None = None


class MonitorStateSummary(BaseModel):
    monitor_id: UUID
    monitor_name: str
    target_id: UUID
    target_name: str
    probe_type: ProbeType
    headline: MonitorHeadline
    effective_agents: int
    healthy_agents: int
    unhealthy_agents: int
    unavailable_agents: int
    coverage_percent: float = Field(ge=0, le=100)
    agents: list[MonitorAgentState]


class IcmpProbeResult(BaseModel):
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


class HttpProbeResult(BaseModel):
    method: str
    scheme: str
    status_code: int | None
    redirect_count: int
    response_size_bytes: int | None
    dns_ms: float | None
    connect_ms: float | None
    tls_ms: float | None
    ttfb_ms: float | None
    total_ms: float | None
    assertions_total: int
    assertions_failed: int
    final_url_redacted: str | None


class TcpProbeResult(BaseModel):
    port: int
    address_used: str | None
    connect_ms: float | None


class DnsProbeResult(BaseModel):
    resolver_address: str
    query_name: str
    query_type: str
    response_code: str | None
    response_ms: float | None
    answer_count: int
    answers: list[dict[str, Any]]
    truncated: bool
    authoritative: bool
    assertions_total: int
    assertions_failed: int


class TlsProbeResult(BaseModel):
    port: int
    server_name: str
    protocol_version: str | None
    cipher_suite: str | None
    handshake_ms: float | None
    certificate_present: bool
    hostname_valid: bool | None
    chain_valid: bool | None
    not_before: datetime | None
    not_after: datetime | None
    days_remaining: float | None
    subject_name: str | None
    issuer_name: str | None
    serial_number: str | None
    fingerprint_sha256: str | None


ProbeResult = IcmpProbeResult | HttpProbeResult | TcpProbeResult | DnsProbeResult | TlsProbeResult


class ProbeHistoryPoint(ObservationSummary):
    result: ProbeResult | None
