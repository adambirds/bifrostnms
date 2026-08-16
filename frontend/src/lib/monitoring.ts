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
