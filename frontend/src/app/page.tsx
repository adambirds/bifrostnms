import Link from 'next/link'

import { IcmpGraph, type IcmpPoint } from '@/app/icmp-graph'
import {
  formatTimestamp,
  headlineLabel,
  statusClass,
} from '@/lib/dashboard'
import { authenticatedApiFetch } from '@/lib/auth'
import type {
  Agent,
  IcmpProbeResult,
  Monitor,
  MonitorStateSummary,
  ObservationSummary,
  ProbeHistoryPoint,
  Target,
} from '@/lib/monitoring'

function isIcmpResult(result: ProbeHistoryPoint['result']): result is IcmpProbeResult {
  return result !== null && 'packets_sent' in result
}

export default async function DashboardPage() {
  const [agents, targets, monitors, states, recent] = await Promise.all([
    authenticatedApiFetch<Agent[]>('/monitoring/agents'),
    authenticatedApiFetch<Target[]>('/monitoring/targets'),
    authenticatedApiFetch<Monitor[]>('/monitoring/monitors'),
    authenticatedApiFetch<MonitorStateSummary[]>('/monitoring/dashboard/current-state'),
    authenticatedApiFetch<ObservationSummary[]>(
      '/monitoring/dashboard/recent-observations?limit=20',
    ),
  ])
  const monitorNames = new Map(monitors.map((monitor) => [monitor.id, monitor.name]))
  const agentNames = new Map(agents.map((agent) => [agent.id, agent.name]))
  const healthy = states.filter((state) => state.headline === 'healthy').length
  const attention = states.filter(
    (state) => state.headline === 'degraded' || state.headline === 'unhealthy',
  ).length
  const unknown = states.filter(
    (state) => state.headline === 'unknown' || state.headline === 'disabled',
  ).length
  const icmpMonitor = monitors.find((monitor) => monitor.probe_type === 'icmp')
  const history = icmpMonitor
    ? await authenticatedApiFetch<ProbeHistoryPoint[]>(
        `/monitoring/dashboard/monitors/${icmpMonitor.id}/history`,
      )
    : []
  const points: IcmpPoint[] = history.flatMap((point) => {
    if (!isIcmpResult(point.result)) return []
    return [
      {
        scheduled_at: point.scheduled_at,
        agent_id: point.agent_id,
        packet_loss_percent: point.result.packet_loss_percent,
        min_rtt_ms: point.result.min_rtt_ms,
        median_rtt_ms: point.result.median_rtt_ms,
        max_rtt_ms: point.result.max_rtt_ms,
        rtt_samples_ms: point.result.rtt_samples_ms,
      },
    ]
  })

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Network overview</span>
          <h1>Overview</h1>
          <p>
            Current distributed health, monitoring coverage and recently received
            observations.
          </p>
        </div>
      </div>
      <div className="cards overview-cards">
        <section className="card">
          <span className="muted">Healthy monitors</span>
          <strong>{healthy}</strong>
          <span className="status-ok">Distributed agreement</span>
        </section>
        <section className="card">
          <span className="muted">Needs attention</span>
          <strong>{attention}</strong>
          <span className={attention ? 'status-warning' : 'status-muted'}>
            Degraded or unhealthy
          </span>
        </section>
        <section className="card">
          <span className="muted">Unknown / inactive</span>
          <strong>{unknown}</strong>
          <span className="status-muted">Missing, pending or unassigned</span>
        </section>
        <section className="card">
          <span className="muted">Monitoring estate</span>
          <strong>{agents.length}</strong>
          <span className="muted">
            {targets.length} targets · {monitors.length} monitors
          </span>
        </section>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Current state</span>
            <h2>Distributed monitors</h2>
          </div>
          <span className="muted">{states.length} configured</span>
        </div>
        {states.length ? (
          <div className="resource-table-wrap">
            <table className="resource-table">
              <thead>
                <tr>
                  <th>Monitor</th>
                  <th>Target</th>
                  <th>State</th>
                  <th>Coverage</th>
                  <th>Agents</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {states.map((state) => (
                  <tr key={state.monitor_id}>
                    <td>
                      <strong>{state.monitor_name}</strong>
                      <div className="muted">{state.probe_type.toUpperCase()}</div>
                    </td>
                    <td>{state.target_name}</td>
                    <td>
                      <span className={statusClass(state.headline)}>
                        {headlineLabel(state.headline)}
                      </span>
                    </td>
                    <td>
                      {state.coverage_percent.toFixed(0)}%
                      <div className="muted">
                        {state.healthy_agents} healthy · {state.unhealthy_agents} unhealthy ·{' '}
                        {state.unavailable_agents} unavailable
                      </div>
                    </td>
                    <td>{state.effective_agents}</td>
                    <td>
                      <Link
                        className="secondary compact-action"
                        href={`/monitors/${state.monitor_id}`}
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <strong>No monitors configured</strong>
            <span>Create a target, monitor and assignment to begin monitoring.</span>
          </div>
        )}
      </section>

      {icmpMonitor ? (
        <section className="panel latency-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Last 24 hours</span>
              <h2>{icmpMonitor.name}</h2>
            </div>
            <Link className="secondary compact-action" href={`/monitors/${icmpMonitor.id}`}>
              Explore history
            </Link>
          </div>
          <IcmpGraph
            agentNames={Object.fromEntries(agentNames)}
            intervalSeconds={icmpMonitor.interval_seconds}
            points={points}
          />
        </section>
      ) : null}

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Control-plane receipt order</span>
            <h2>Recent observations</h2>
          </div>
          <span className="muted">Latest {recent.length}</span>
        </div>
        {recent.length ? (
          <div className="resource-table-wrap">
            <table className="resource-table">
              <thead>
                <tr>
                  <th>Received</th>
                  <th>Monitor</th>
                  <th>Agent</th>
                  <th>Probe</th>
                  <th>Execution</th>
                  <th>Assessment</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((observation) => (
                  <tr key={observation.observation_id}>
                    <td>{formatTimestamp(observation.received_at)}</td>
                    <td>
                      <Link href={`/monitors/${observation.monitor_id}`}>
                        {monitorNames.get(observation.monitor_id) ?? observation.monitor_id}
                      </Link>
                    </td>
                    <td>{agentNames.get(observation.agent_id) ?? observation.agent_id}</td>
                    <td>{observation.probe_type.toUpperCase()}</td>
                    <td>{observation.execution_status}</td>
                    <td>
                      <span className={statusClass(observation.assessment)}>
                        {observation.assessment}
                      </span>
                    </td>
                    <td>{observation.error_code ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <strong>No observations received</strong>
            <span>
              This is an explicit no-data state. Once enrolled agents execute assigned
              monitors, observations will appear here.
            </span>
          </div>
        )}
      </section>
    </>
  )
}
