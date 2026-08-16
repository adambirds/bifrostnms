import type {
  AvailabilityState,
  MonitorHeadline,
  ObservationSummary,
} from '@/lib/monitoring'

const availabilityLabels: Record<AvailabilityState, string> = {
  pending_configuration: 'Pending configuration',
  no_data_yet: 'No data yet',
  healthy: 'Healthy',
  unhealthy: 'Unhealthy',
  probe_error: 'Probe error',
  overdue: 'Missing data',
  agent_stale: 'Agent stale',
  agent_offline: 'Agent offline',
  disabled: 'Disabled',
}

const headlineLabels: Record<MonitorHeadline, string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  unhealthy: 'Unhealthy',
  unknown: 'Unknown',
  disabled: 'Disabled',
}

export function availabilityLabel(state: AvailabilityState): string {
  return availabilityLabels[state]
}

export function headlineLabel(headline: MonitorHeadline): string {
  return headlineLabels[headline]
}

export function statusClass(
  state: AvailabilityState | MonitorHeadline | ObservationSummary['assessment'],
): string {
  if (state === 'healthy') return 'status-ok'
  if (state === 'unhealthy') return 'status-danger'
  if (state === 'degraded' || state === 'probe_error' || state === 'overdue') {
    return 'status-warning'
  }
  return 'status-muted'
}

export function formatTimestamp(value: string | null): string {
  if (!value) return 'Never'
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value))
}

export function formatDuration(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(1)} ms`
}
