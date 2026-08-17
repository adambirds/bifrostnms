import Link from 'next/link'
import { notFound } from 'next/navigation'

import { formatTimestamp, headlineLabel, statusClass } from '@/lib/dashboard'
import { authenticatedApiFetch } from '@/lib/auth'
import type {
  DnsProbeResult,
  HttpProbeResult,
  IcmpProbeResult,
  TargetMonitorSummary,
  TargetOperationalSummary,
  TcpProbeResult,
  TlsProbeResult,
} from '@/lib/monitoring'

type PageProps = {
  params: Promise<{ targetId: string }>
}

function metricRows(monitor: TargetMonitorSummary): Array<[string, string]> {
  const result = monitor.latest_result
  if (!result) return [['Measurement', monitor.latest_error_code ?? 'No measurement yet']]

  if (monitor.probe_type === 'icmp' && 'packets_sent' in result) {
    const icmp = result as IcmpProbeResult
    return [
      ['Median RTT', icmp.median_rtt_ms === null ? '—' : `${icmp.median_rtt_ms.toFixed(1)} ms`],
      ['Packet loss', `${icmp.packet_loss_percent.toFixed(1)}%`],
      ['Jitter', icmp.jitter_ms === null ? '—' : `${icmp.jitter_ms.toFixed(1)} ms`],
    ]
  }
  if (monitor.probe_type === 'http' && 'status_code' in result) {
    const http = result as HttpProbeResult
    return [
      ['HTTP status', String(http.status_code ?? '—')],
      ['Total', http.total_ms === null ? '—' : `${http.total_ms.toFixed(1)} ms`],
      ['Assertions', `${http.assertions_failed}/${http.assertions_total} failed`],
    ]
  }
  if (monitor.probe_type === 'tcp' && 'port' in result && 'connect_ms' in result) {
    const tcp = result as TcpProbeResult
    return [
      ['Port', String(tcp.port)],
      ['Connect', tcp.connect_ms === null ? '—' : `${tcp.connect_ms.toFixed(1)} ms`],
      ['Address', tcp.address_used ?? '—'],
    ]
  }
  if (monitor.probe_type === 'dns' && 'query_name' in result) {
    const dns = result as DnsProbeResult
    return [
      ['Response', dns.response_code ?? '—'],
      ['Duration', dns.response_ms === null ? '—' : `${dns.response_ms.toFixed(1)} ms`],
      ['Answers', String(dns.answer_count)],
    ]
  }
  const tls = result as TlsProbeResult
  return [
    ['Protocol', tls.protocol_version ?? '—'],
    ['Handshake', tls.handshake_ms === null ? '—' : `${tls.handshake_ms.toFixed(1)} ms`],
    ['Expires', tls.days_remaining === null ? '—' : `${tls.days_remaining.toFixed(0)} days`],
  ]
}

export default async function TargetDetailPage({ params }: PageProps) {
  const { targetId } = await params
  let target: TargetOperationalSummary
  try {
    target = await authenticatedApiFetch<TargetOperationalSummary>(
      `/monitoring/dashboard/targets/${targetId}`,
    )
  } catch {
    notFound()
  }

  const agents = new Map<string, string>()
  for (const monitor of target.monitors) {
    if (monitor.latest_agent_id && monitor.latest_agent_name) {
      agents.set(monitor.latest_agent_id, monitor.latest_agent_name)
    }
  }

  return (
    <>
      <div className="monitor-detail-heading">
        <nav className="monitor-breadcrumbs" aria-label="Breadcrumb">
          <Link href="/targets">Targets</Link><span>›</span><span>{target.target_name}</span>
        </nav>
        <div className="monitor-title-row">
          <div>
            <div className="monitor-title-line">
              <h1>{target.target_name}</h1>
              <span className={statusClass(target.headline)}>{headlineLabel(target.headline)}</span>
            </div>
            <div className="monitor-meta-line">
              <span>{target.address}</span><i />
              <span>{target.monitor_count} monitors</span><i />
              <span>{target.agent_count} vantage points</span>
            </div>
            {target.description ? <p className="target-description">{target.description}</p> : null}
          </div>
          <div className="page-actions">
            <Link className="secondary compact-action" href="/targets">Back to targets</Link>
          </div>
        </div>
      </div>

      <div className="cards target-health-cards">
        <section className="card"><span className="muted">Overall state</span><strong className="target-state-value">{headlineLabel(target.headline)}</strong><span className={statusClass(target.headline)}>{target.healthy_monitors} healthy monitors</span></section>
        <section className="card"><span className="muted">Monitoring coverage</span><strong>{target.monitor_count}</strong><span className="muted">{target.degraded_monitors + target.unhealthy_monitors} need attention · {target.unknown_monitors} unknown</span></section>
        <section className="card"><span className="muted">Vantage points</span><strong>{target.agent_count}</strong><span className="muted">Effective agents across monitors</span></section>
      </div>

      <section className="panel">
        <div className="panel-heading"><div><span className="eyebrow">Current state</span><h2>Monitors</h2></div><span className="muted">{target.monitors.length} configured</span></div>
        {target.monitors.length ? (
          <div className="target-monitor-grid">
            {target.monitors.map((monitor) => (
              <article className="target-monitor-card" key={monitor.monitor_id}>
                <div className="target-monitor-card-heading">
                  <div><span className="probe-badge">{monitor.probe_type.toUpperCase()}</span><h3>{monitor.monitor_name}</h3></div>
                  <span className={statusClass(monitor.headline)}>{headlineLabel(monitor.headline)}</span>
                </div>
                <dl className="target-monitor-metrics">
                  {metricRows(monitor).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
                </dl>
                <div className="target-monitor-card-footer">
                  <span className="muted">{monitor.healthy_agents}/{monitor.effective_agents} healthy agents · {monitor.coverage_percent.toFixed(0)}% coverage</span>
                  <Link className="secondary compact-action" href={`/monitors/${monitor.monitor_id}`}>Open monitor</Link>
                </div>
                {monitor.latest_scheduled_at ? <small className="muted">Latest: {formatTimestamp(monitor.latest_scheduled_at)}{monitor.latest_agent_name ? ` from ${monitor.latest_agent_name}` : ''}</small> : null}
              </article>
            ))}
          </div>
        ) : <div className="empty-state"><strong>No monitors configured</strong><span>This target exists but is not currently monitored.</span></div>}
      </section>

      <section className="panel">
        <div className="panel-heading"><div><span className="eyebrow">Vantage points</span><h2>Monitoring from</h2></div><span className="muted">{agents.size} recently reporting</span></div>
        {agents.size ? <div className="agent-pill-grid">{[...agents.entries()].map(([id, name]) => <span className="agent-pill" key={id}><i />{name}</span>)}</div> : <div className="empty-state compact-empty-state"><strong>No recent agent data</strong><span>Agent names appear here after observations arrive.</span></div>}
      </section>
    </>
  )
}
