import Link from 'next/link'

import { formatTimestamp, headlineLabel, statusClass } from '@/lib/dashboard'
import { authenticatedApiFetch } from '@/lib/auth'
import type {
  DashboardOverview,
  DnsProbeResult,
  HttpProbeResult,
  IcmpProbeResult,
  ObservationSummary,
  TargetMonitorSummary,
  TcpProbeResult,
  TlsProbeResult,
} from '@/lib/monitoring'

function monitorMetric(monitor: TargetMonitorSummary): string {
  const result = monitor.latest_result
  if (!result) return monitor.latest_error_code ?? 'No measurement yet'
  if (monitor.probe_type === 'icmp' && 'packets_sent' in result) {
    const icmp = result as IcmpProbeResult
    return `${icmp.median_rtt_ms?.toFixed(1) ?? '—'} ms · ${icmp.packet_loss_percent.toFixed(1)}% loss`
  }
  if (monitor.probe_type === 'http' && 'status_code' in result) {
    const http = result as HttpProbeResult
    return `${http.status_code ?? '—'} · ${http.total_ms?.toFixed(1) ?? '—'} ms`
  }
  if (monitor.probe_type === 'tcp' && 'connect_ms' in result && 'port' in result) {
    const tcp = result as TcpProbeResult
    return `:${tcp.port} · ${tcp.connect_ms?.toFixed(1) ?? '—'} ms`
  }
  if (monitor.probe_type === 'dns' && 'query_name' in result) {
    const dns = result as DnsProbeResult
    return `${dns.response_code ?? '—'} · ${dns.response_ms?.toFixed(1) ?? '—'} ms`
  }
  const tls = result as TlsProbeResult
  return `${tls.protocol_version ?? 'TLS'} · ${tls.days_remaining?.toFixed(0) ?? '—'} days`
}

export default async function DashboardPage() {
  const [overview, recent] = await Promise.all([
    authenticatedApiFetch<DashboardOverview>('/monitoring/dashboard/overview'),
    authenticatedApiFetch<ObservationSummary[]>(
      '/monitoring/dashboard/recent-observations?limit=12',
    ),
  ])
  const monitorNames = new Map(
    overview.targets.flatMap((target) =>
      target.monitors.map((monitor) => [monitor.monitor_id, monitor.monitor_name] as const),
    ),
  )
  const targetByMonitor = new Map(
    overview.targets.flatMap((target) =>
      target.monitors.map((monitor) => [monitor.monitor_id, target] as const),
    ),
  )
  const attentionTargets = overview.targets.filter(
    (target) => target.headline === 'degraded' || target.headline === 'unhealthy',
  )

  return (
    <>
      <div className="page-heading dashboard-heading">
        <div>
          <span className="eyebrow">Operations</span>
          <h1>Network overview</h1>
          <p>Start with what needs attention, then drill into a target or individual monitor.</p>
        </div>
      </div>

      <div className="cards estate-summary-cards">
        <section className="card estate-card estate-card-healthy">
          <span className="muted">Healthy targets</span>
          <strong>{overview.healthy_targets}</strong>
          <span className="status-ok">Operating normally</span>
        </section>
        <section className="card estate-card estate-card-warning">
          <span className="muted">Degraded</span>
          <strong>{overview.degraded_targets}</strong>
          <span className={overview.degraded_targets ? 'status-warning' : 'status-muted'}>
            Partial or mixed health
          </span>
        </section>
        <section className="card estate-card estate-card-danger">
          <span className="muted">Unhealthy</span>
          <strong>{overview.unhealthy_targets}</strong>
          <span className={overview.unhealthy_targets ? 'status-danger' : 'status-muted'}>
            Requires attention
          </span>
        </section>
        <section className="card estate-card">
          <span className="muted">Unknown / inactive</span>
          <strong>{overview.unknown_targets}</strong>
          <span className="status-muted">No trustworthy current state</span>
        </section>
      </div>

      <section className="panel dashboard-estate-strip">
        <div className="estate-stat"><span>Targets</span><strong>{overview.target_count}</strong></div>
        <div className="estate-stat"><span>Monitors</span><strong>{overview.monitor_count}</strong></div>
        <div className="estate-stat"><span>Agents</span><strong>{overview.agent_count}</strong></div>
      </section>

      <section className="panel attention-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Priority</span>
            <h2>Needs attention</h2>
          </div>
          <span className="muted">{attentionTargets.length} targets</span>
        </div>
        {attentionTargets.length ? (
          <div className="attention-grid">
            {attentionTargets.map((target) => (
              <Link className="attention-card" href={`/targets/${target.target_id}`} key={target.target_id}>
                <div>
                  <span className={statusClass(target.headline)}>{headlineLabel(target.headline)}</span>
                  <strong>{target.target_name}</strong>
                  <code>{target.address}</code>
                </div>
                <div className="attention-monitor-list">
                  {target.monitors
                    .filter((monitor) => monitor.headline !== 'healthy')
                    .slice(0, 3)
                    .map((monitor) => (
                      <span key={monitor.monitor_id}>
                        <b>{monitor.probe_type.toUpperCase()}</b> {monitorMetric(monitor)}
                      </span>
                    ))}
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="empty-state compact-empty-state">
            <strong>Nothing needs attention</strong>
            <span>All targets with trustworthy current state are healthy.</span>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Estate</span>
            <h2>Targets</h2>
          </div>
          <Link className="secondary compact-action" href="/targets">Manage targets</Link>
        </div>
        {overview.targets.length ? (
          <div className="resource-table-wrap">
            <table className="resource-table target-overview-table">
              <thead>
                <tr>
                  <th>Target</th>
                  <th>Overall</th>
                  <th>Monitors</th>
                  <th>Latest measurements</th>
                  <th>Agents</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {overview.targets.map((target) => (
                  <tr key={target.target_id}>
                    <td>
                      <Link href={`/targets/${target.target_id}`}><strong>{target.target_name}</strong></Link>
                      <div className="muted"><code>{target.address}</code></div>
                    </td>
                    <td><span className={statusClass(target.headline)}>{headlineLabel(target.headline)}</span></td>
                    <td>
                      {target.monitor_count}
                      <div className="muted">{target.healthy_monitors} healthy · {target.unhealthy_monitors + target.degraded_monitors} attention</div>
                    </td>
                    <td>
                      <div className="target-monitor-chips">
                        {target.monitors.slice(0, 4).map((monitor) => (
                          <span className={`monitor-chip monitor-chip-${monitor.headline}`} key={monitor.monitor_id}>
                            <b>{monitor.probe_type.toUpperCase()}</b> {monitorMetric(monitor)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>{target.agent_count}</td>
                    <td><Link className="secondary compact-action" href={`/targets/${target.target_id}`}>View</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state"><strong>No targets yet</strong><span>Create a target to begin monitoring.</span></div>
        )}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Latest activity</span>
            <h2>Recent observations</h2>
          </div>
          <span className="muted">Latest {recent.length}</span>
        </div>
        {recent.length ? (
          <div className="resource-table-wrap">
            <table className="resource-table compact-observation-table">
              <thead><tr><th>Received</th><th>Target</th><th>Monitor</th><th>Probe</th><th>State</th><th>Error</th></tr></thead>
              <tbody>
                {recent.map((observation) => {
                  const target = targetByMonitor.get(observation.monitor_id)
                  return (
                    <tr key={observation.observation_id}>
                      <td>{formatTimestamp(observation.received_at)}</td>
                      <td>{target ? <Link href={`/targets/${target.target_id}`}>{target.target_name}</Link> : '—'}</td>
                      <td><Link href={`/monitors/${observation.monitor_id}`}>{monitorNames.get(observation.monitor_id) ?? observation.monitor_id}</Link></td>
                      <td>{observation.probe_type.toUpperCase()}</td>
                      <td><span className={statusClass(observation.assessment)}>{observation.assessment}</span></td>
                      <td>{observation.error_code ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </>
  )
}
