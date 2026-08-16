import Link from 'next/link'
import { notFound } from 'next/navigation'

import {
  IcmpGraph,
  type IcmpObservationMeta,
  type IcmpPoint,
} from '@/app/icmp-graph'
import {
  formatDuration,
  formatTimestamp,
  statusClass,
} from '@/lib/dashboard'
import { authenticatedApiFetch } from '@/lib/auth'
import type {
  Agent,
  DnsProbeResult,
  HttpProbeResult,
  IcmpProbeResult,
  Monitor,
  MonitorStateSummary,
  ProbeHistoryPoint,
  TcpProbeResult,
  Target,
  TlsProbeResult,
} from '@/lib/monitoring'

const ranges = {
  '1h': { label: '1 hour', milliseconds: 60 * 60 * 1000 },
  '6h': { label: '6 hours', milliseconds: 6 * 60 * 60 * 1000 },
  '24h': { label: '24 hours', milliseconds: 24 * 60 * 60 * 1000 },
  '7d': { label: '7 days', milliseconds: 7 * 24 * 60 * 60 * 1000 },
  '30d': { label: '30 days', milliseconds: 30 * 24 * 60 * 60 * 1000 },
} as const

type RangeKey = keyof typeof ranges

type PageProps = {
  params: Promise<{ monitorId: string }>
  searchParams: Promise<{ range?: string }>
}

function isIcmpResult(result: ProbeHistoryPoint['result']): result is IcmpProbeResult {
  return result !== null && 'packets_sent' in result
}

function isHttpResult(result: ProbeHistoryPoint['result']): result is HttpProbeResult {
  return result !== null && 'status_code' in result && 'total_ms' in result
}

function isTcpResult(result: ProbeHistoryPoint['result']): result is TcpProbeResult {
  return result !== null && 'connect_ms' in result && 'port' in result && !('scheme' in result)
}

function isDnsResult(result: ProbeHistoryPoint['result']): result is DnsProbeResult {
  return result !== null && 'query_name' in result
}

function isTlsResult(result: ProbeHistoryPoint['result']): result is TlsProbeResult {
  return result !== null && 'certificate_present' in result
}

function ObservationError({ point }: { point: ProbeHistoryPoint }) {
  if (!point.error_code && !point.error_message) return <>—</>
  return (
    <span className="observation-error">
      {point.error_code ?? point.error_category ?? 'probe_error'}
      {point.error_message ? ` — ${point.error_message}` : ''}
    </span>
  )
}

function ProbeHistoryTable({
  monitor,
  history,
  agentNames,
}: {
  monitor: Monitor
  history: ProbeHistoryPoint[]
  agentNames: Map<string, string>
}) {
  if (!history.length) {
    return (
      <div className="empty-state">
        <strong>No observations in this range</strong>
        <span>
          This is missing data, not a zero or successful measurement. Check assignments,
          agent state and configuration acknowledgement above.
        </span>
      </div>
    )
  }

  return (
    <div className="resource-table-wrap">
      <table className="resource-table observation-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Agent</th>
            <th>State</th>
            {monitor.probe_type === 'icmp' ? (
              <>
                <th>Loss</th>
                <th>Median</th>
                <th>P95</th>
                <th>Jitter</th>
              </>
            ) : null}
            {monitor.probe_type === 'http' ? (
              <>
                <th>Status</th>
                <th>Total</th>
                <th>DNS / Connect / TLS / TTFB</th>
                <th>Assertions</th>
              </>
            ) : null}
            {monitor.probe_type === 'tcp' ? (
              <>
                <th>Address</th>
                <th>Port</th>
                <th>Connect</th>
              </>
            ) : null}
            {monitor.probe_type === 'dns' ? (
              <>
                <th>Response</th>
                <th>Duration</th>
                <th>Answers</th>
              </>
            ) : null}
            {monitor.probe_type === 'tls' ? (
              <>
                <th>Protocol</th>
                <th>Handshake</th>
                <th>Certificate</th>
                <th>Expires</th>
              </>
            ) : null}
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {[...history].reverse().map((point) => {
            const result = point.result
            return (
              <tr key={point.observation_id}>
                <td>{formatTimestamp(point.scheduled_at)}</td>
                <td>{agentNames.get(point.agent_id) ?? point.agent_id}</td>
                <td>
                  <span className={statusClass(point.assessment)}>{point.assessment}</span>
                  {point.execution_status === 'failed' ? (
                    <div className="muted">Execution failed</div>
                  ) : null}
                </td>
                {monitor.probe_type === 'icmp' ? (
                  isIcmpResult(result) ? (
                    <>
                      <td>{result.packet_loss_percent.toFixed(1)}%</td>
                      <td>{formatDuration(result.median_rtt_ms)}</td>
                      <td>{formatDuration(result.p95_rtt_ms)}</td>
                      <td>{formatDuration(result.jitter_ms)}</td>
                    </>
                  ) : (
                    <td colSpan={4}>No typed result</td>
                  )
                ) : null}
                {monitor.probe_type === 'http' ? (
                  isHttpResult(result) ? (
                    <>
                      <td>{result.status_code ?? '—'}</td>
                      <td>{formatDuration(result.total_ms)}</td>
                      <td>
                        {[
                          result.dns_ms,
                          result.connect_ms,
                          result.tls_ms,
                          result.ttfb_ms,
                        ]
                          .map(formatDuration)
                          .join(' / ')}
                      </td>
                      <td>
                        {result.assertions_failed}/{result.assertions_total} failed
                      </td>
                    </>
                  ) : (
                    <td colSpan={4}>No typed result</td>
                  )
                ) : null}
                {monitor.probe_type === 'tcp' ? (
                  isTcpResult(result) ? (
                    <>
                      <td>{result.address_used ?? '—'}</td>
                      <td>{result.port}</td>
                      <td>{formatDuration(result.connect_ms)}</td>
                    </>
                  ) : (
                    <td colSpan={3}>No typed result</td>
                  )
                ) : null}
                {monitor.probe_type === 'dns' ? (
                  isDnsResult(result) ? (
                    <>
                      <td>
                        {result.response_code ?? '—'} · {result.query_type}{' '}
                        {result.query_name}
                      </td>
                      <td>{formatDuration(result.response_ms)}</td>
                      <td>
                        <code className="answer-preview">
                          {result.answers.length
                            ? JSON.stringify(result.answers)
                            : 'No answers'}
                        </code>
                      </td>
                    </>
                  ) : (
                    <td colSpan={3}>No typed result</td>
                  )
                ) : null}
                {monitor.probe_type === 'tls' ? (
                  isTlsResult(result) ? (
                    <>
                      <td>{result.protocol_version ?? '—'}</td>
                      <td>{formatDuration(result.handshake_ms)}</td>
                      <td>
                        {result.certificate_present ? result.subject_name ?? 'Present' : 'Missing'}
                      </td>
                      <td>
                        {result.not_after ? formatTimestamp(result.not_after) : '—'}
                        {result.days_remaining !== null ? (
                          <div className="muted">
                            {result.days_remaining.toFixed(1)} days remaining
                          </div>
                        ) : null}
                      </td>
                    </>
                  ) : (
                    <td colSpan={4}>No typed result</td>
                  )
                ) : null}
                <td>
                  <ObservationError point={point} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default async function MonitorDetailPage({ params, searchParams }: PageProps) {
  const { monitorId } = await params
  const requestedRange = (await searchParams).range
  const rangeKey: RangeKey =
    requestedRange && requestedRange in ranges ? (requestedRange as RangeKey) : '24h'
  const range = ranges[rangeKey]
  const end = new Date()
  const start = new Date(end.getTime() - range.milliseconds)

  let monitor: Monitor
  try {
    monitor = await authenticatedApiFetch<Monitor>(`/monitoring/monitors/${monitorId}`)
  } catch {
    notFound()
  }

  const [targets, agents, states, history] = await Promise.all([
    authenticatedApiFetch<Target[]>('/monitoring/targets'),
    authenticatedApiFetch<Agent[]>('/monitoring/agents'),
    authenticatedApiFetch<MonitorStateSummary[]>('/monitoring/dashboard/current-state'),
    authenticatedApiFetch<ProbeHistoryPoint[]>(
      `/monitoring/dashboard/monitors/${monitorId}/history?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
    ),
  ])
  const target = targets.find((item) => item.id === monitor.target_id)
  const state = states.find((item) => item.monitor_id === monitor.id)
  const agentNames = new Map(agents.map((agent) => [agent.id, agent.name]))
  const graphAgentNames = Object.fromEntries(agentNames)
  const icmpPoints: IcmpPoint[] = history.flatMap((point) => {
    if (!isIcmpResult(point.result)) return []
    return [
      {
        scheduled_at: point.scheduled_at,
        agent_id: point.agent_id,
        packets_sent: point.result.packets_sent,
        packets_received: point.result.packets_received,
        packet_loss_percent: point.result.packet_loss_percent,
        min_rtt_ms: point.result.min_rtt_ms,
        avg_rtt_ms: point.result.avg_rtt_ms,
        median_rtt_ms: point.result.median_rtt_ms,
        max_rtt_ms: point.result.max_rtt_ms,
        p95_rtt_ms: point.result.p95_rtt_ms,
        jitter_ms: point.result.jitter_ms,
        rtt_samples_ms: point.result.rtt_samples_ms,
      },
    ]
  })
  const icmpObservations: IcmpObservationMeta[] = history.map((point) => ({
    scheduled_at: point.scheduled_at,
    agent_id: point.agent_id,
    execution_status: point.execution_status,
    assessment: point.assessment,
  }))
  const packetCount = icmpPoints.at(-1)?.packets_sent

  return (
    <>
      <div className="monitor-detail-heading">
        <nav className="monitor-breadcrumbs" aria-label="Breadcrumb">
          <Link href="/monitors">Monitors</Link>
          <span>›</span>
          <span>{monitor.name}</span>
        </nav>
        <div className="monitor-title-row">
          <div>
            <div className="monitor-title-line">
              <h1>{monitor.name}</h1>
              <span className={state ? statusClass(state.headline) : 'status-muted'}>
                {state?.headline ?? 'Unknown'}
              </span>
            </div>
            <div className="monitor-meta-line">
              <span>{monitor.probe_type.toUpperCase()}</span>
              <i />
              <span>Every {monitor.interval_seconds} seconds</span>
              <i />
              <span>{monitor.timeout_seconds}s timeout</span>
              {packetCount ? <><i /><span>{packetCount} packets</span></> : null}
              <i />
              <span>{target?.address ?? 'Unknown address'}</span>
            </div>
          </div>
          <div className="page-actions">
            <Link className="secondary compact-action" href="/monitors">
              Back to monitors
            </Link>
            <Link className="secondary compact-action" href={`/monitors/${monitor.id}/edit`}>
              Edit monitor
            </Link>
          </div>
        </div>
      </div>

      <section className="panel monitor-history-panel">
        <div className="panel-heading history-heading">
          <div>
            <span className="eyebrow">Historical measurements</span>
            <h2>{range.label}</h2>
          </div>
          <nav className="range-picker" aria-label="History range">
            {(Object.keys(ranges) as RangeKey[]).map((key) => (
              <Link
                aria-current={key === rangeKey ? 'page' : undefined}
                className={key === rangeKey ? 'active' : undefined}
                href={`/monitors/${monitor.id}?range=${key}`}
                key={key}
              >
                {key}
              </Link>
            ))}
          </nav>
        </div>
        {monitor.probe_type === 'icmp' ? (
          <IcmpGraph
            agentNames={graphAgentNames}
            intervalSeconds={monitor.interval_seconds}
            observations={icmpObservations}
            points={icmpPoints}
            rangeEnd={end.toISOString()}
            rangeStart={start.toISOString()}
          />
        ) : (
          <ProbeHistoryTable agentNames={agentNames} history={history} monitor={monitor} />
        )}
      </section>

      {monitor.probe_type === 'icmp' ? (
        <section className="panel raw-observations-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Raw observations</span>
              <h2>Recent probe executions</h2>
            </div>
            <span className="muted">{history.length} rows in this range</span>
          </div>
          <ProbeHistoryTable agentNames={agentNames} history={history} monitor={monitor} />
        </section>
      ) : null}
    </>
  )
}
