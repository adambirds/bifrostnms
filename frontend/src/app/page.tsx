import {IcmpGraph, type IcmpPoint} from '@/app/icmp-graph'
import {authenticatedApiFetch} from '@/lib/auth'
import type {Agent, Monitor, Target} from '@/lib/monitoring'

export default async function DashboardPage() {
  const [agents, targets, monitors] = await Promise.all([
    authenticatedApiFetch<Agent[]>('/monitoring/agents'),
    authenticatedApiFetch<Target[]>('/monitoring/targets'),
    authenticatedApiFetch<Monitor[]>('/monitoring/monitors'),
  ])
  const icmpMonitor = monitors.find(monitor => monitor.probe_type === 'icmp')
  const points = icmpMonitor
    ? await authenticatedApiFetch<IcmpPoint[]>(
        `/monitoring/monitors/${icmpMonitor.id}/icmp/history`,
      )
    : []

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Network overview</span>
          <h1>Overview</h1>
          <p>Current configuration and recent distributed measurements.</p>
        </div>
      </div>
      <div className="cards">
        <section className="card">
          <span className="muted">Configured agents</span>
          <strong>{agents.length}</strong>
        </section>
        <section className="card">
          <span className="muted">Targets</span>
          <strong>{targets.length}</strong>
        </section>
        <section className="card">
          <span className="muted">Monitors</span>
          <strong>{monitors.length}</strong>
        </section>
      </div>
      <section className="panel latency-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Last 24 hours</span>
            <h2>{icmpMonitor?.name ?? 'ICMP latency'}</h2>
          </div>
          <span className="muted">{points.length} observations · milliseconds</span>
        </div>
        <IcmpGraph points={points} />
      </section>
    </>
  )
}
