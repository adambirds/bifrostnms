export type ProbeType = 'icmp' | 'http' | 'tcp' | 'dns' | 'tls'

export type Agent = {
  id: string
  realm_id: string
  name: string
  description: string | null
  enabled: boolean
  archived_at: string | null
  created_at: string
  updated_at: string
}

export type AgentEnrolmentToken = {
  id: string
  agent_id: string
  enrolment_token: string
  expires_at: string
}

export type AgentGroup = {
  id: string
  realm_id: string
  parent_id: string | null
  name: string
  description: string | null
  enabled: boolean
  archived_at: string | null
  created_at: string
  updated_at: string
}

export type AgentGroupMembership = {
  id: string
  realm_id: string
  agent_group_id: string
  agent_id: string
  created_at: string
}

export type Target = {
  id: string
  realm_id: string
  name: string
  description: string | null
  address: string
  enabled: boolean
  archived_at: string | null
  created_at: string
  updated_at: string
}

export type TargetGroup = {
  id: string
  realm_id: string
  parent_id: string | null
  name: string
  description: string | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export type TargetGroupMembership = {
  id: string
  realm_id: string
  target_group_id: string
  target_id: string
  created_at: string
}

export type Monitor = {
  id: string
  realm_id: string
  target_id: string
  name: string
  description: string | null
  probe_type: ProbeType
  interval_seconds: number
  timeout_seconds: number
  configuration: Record<string, unknown>
  enabled: boolean
  revision: number
  archived_at: string | null
  created_at: string
  updated_at: string
}

export type BulkMonitorSkippedTarget = {
  target_id: string
  target_name: string
  reason: string
}

export type BulkMonitorCreateResponse = {
  created: Monitor[]
  skipped: BulkMonitorSkippedTarget[]
}

export type MonitorAgentAssignment = {
  id: string
  realm_id: string
  monitor_id: string
  agent_id: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export type MonitorAgentGroupAssignment = {
  id: string
  realm_id: string
  monitor_id: string
  agent_group_id: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export type AgentStatus = {
  agent_id: string
  online: boolean
  last_heartbeat_at: string | null
  agent_version: string | null
  platform: string | null
  architecture: string | null
  hostname: string | null
  capabilities: Record<string, unknown>
  active_configuration_revision: number
  known_desired_configuration_revision: number
  queue_depth: number
  queue_bytes: number
  oldest_pending_observation_at: string | null
  database_health: string | null
  scheduler_state: string | null
  clock_offset_ms: number | null
  warnings: string[]
}

export type AvailabilityState =
  | 'pending_configuration'
  | 'no_data_yet'
  | 'healthy'
  | 'unhealthy'
  | 'probe_error'
  | 'overdue'
  | 'agent_stale'
  | 'agent_offline'
  | 'disabled'

export type MonitorHeadline =
  'healthy' | 'degraded' | 'unhealthy' | 'unknown' | 'disabled'

export type ObservationSummary = {
  observation_id: string
  scheduled_at: string
  received_at: string
  monitor_id: string
  agent_id: string
  probe_type: ProbeType
  execution_status: 'completed' | 'failed'
  assessment: 'healthy' | 'unhealthy' | 'unknown'
  error_category: string | null
  error_code: string | null
  error_message: string | null
}

export type MonitorAgentState = {
  monitor_id: string
  monitor_name: string
  agent_id: string
  agent_name: string
  probe_type: ProbeType
  availability_state: AvailabilityState
  desired_config_revision: number
  acknowledged_config_revision: number
  last_observation_id: string | null
  last_scheduled_at: string | null
  last_received_at: string | null
  execution_status: 'completed' | 'failed' | null
  assessment: 'healthy' | 'unhealthy' | 'unknown' | null
}

export type MonitorStateSummary = {
  monitor_id: string
  monitor_name: string
  target_id: string
  target_name: string
  probe_type: ProbeType
  headline: MonitorHeadline
  effective_agents: number
  healthy_agents: number
  unhealthy_agents: number
  unavailable_agents: number
  coverage_percent: number
  agents: MonitorAgentState[]
}

export type IcmpProbeResult = {
  packets_sent: number
  packets_received: number
  packet_loss_percent: number
  min_rtt_ms: number | null
  avg_rtt_ms: number | null
  median_rtt_ms: number | null
  max_rtt_ms: number | null
  p95_rtt_ms: number | null
  jitter_ms: number | null
  rtt_samples_ms: number[]
}

export type HttpProbeResult = {
  method: string
  scheme: string
  status_code: number | null
  redirect_count: number
  response_size_bytes: number | null
  dns_ms: number | null
  connect_ms: number | null
  tls_ms: number | null
  ttfb_ms: number | null
  total_ms: number | null
  assertions_total: number
  assertions_failed: number
  final_url_redacted: string | null
}

export type TcpProbeResult = {
  port: number
  address_used: string | null
  connect_ms: number | null
}

export type DnsProbeResult = {
  resolver_address: string
  query_name: string
  query_type: string
  response_code: string | null
  response_ms: number | null
  answer_count: number
  answers: Record<string, unknown>[]
  truncated: boolean
  authoritative: boolean
  assertions_total: number
  assertions_failed: number
}

export type TlsProbeResult = {
  port: number
  server_name: string
  protocol_version: string | null
  cipher_suite: string | null
  handshake_ms: number | null
  certificate_present: boolean
  hostname_valid: boolean | null
  chain_valid: boolean | null
  not_before: string | null
  not_after: string | null
  days_remaining: number | null
  subject_name: string | null
  issuer_name: string | null
  serial_number: string | null
  fingerprint_sha256: string | null
}

export type ProbeResult =
  | IcmpProbeResult
  | HttpProbeResult
  | TcpProbeResult
  | DnsProbeResult
  | TlsProbeResult

export type ProbeHistoryPoint = ObservationSummary & {
  result: ProbeResult | null
}

export type TargetMonitorSummary = {
  monitor_id: string
  monitor_name: string
  probe_type: ProbeType
  headline: MonitorHeadline
  enabled: boolean
  effective_agents: number
  healthy_agents: number
  unhealthy_agents: number
  unavailable_agents: number
  coverage_percent: number
  latest_scheduled_at: string | null
  latest_agent_id: string | null
  latest_agent_name: string | null
  latest_assessment: 'healthy' | 'unhealthy' | 'unknown' | null
  latest_execution_status: 'completed' | 'failed' | null
  latest_error_code: string | null
  latest_result: ProbeResult | null
}

export type TargetOperationalSummary = {
  target_id: string
  target_name: string
  address: string
  description: string | null
  enabled: boolean
  headline: MonitorHeadline
  monitor_count: number
  healthy_monitors: number
  degraded_monitors: number
  unhealthy_monitors: number
  unknown_monitors: number
  agent_count: number
  monitors: TargetMonitorSummary[]
}

export type DashboardOverview = {
  target_count: number
  monitor_count: number
  agent_count: number
  healthy_targets: number
  degraded_targets: number
  unhealthy_targets: number
  unknown_targets: number
  targets: TargetOperationalSummary[]
}
