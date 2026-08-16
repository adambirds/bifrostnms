import {IcmpGraph, type IcmpPoint} from '@/app/icmp-graph'
import {authenticatedApiFetch, requireUser} from '@/lib/auth'
import Link from 'next/link'

const authUrl = process.env.NEXT_PUBLIC_AUTH_URL ?? 'http://localhost:3001'

export default async function DashboardPage() {
  const user = await requireUser()
  const realm = user.realms.find(r => r.id === user.active_realm_id) ?? user.realms[0]
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
    <div className="shell">
      <aside>
        <div className="brand">BifrostNMS</div>
        <nav><Link href="/">Overview</Link><a href="#">Targets</a><a href="#">Agents</a><a href="#">Monitors</a><a href="#">Alerts</a><a href="#">Settings</a></nav>
      </aside>
      <main>
        <div className="top">
          <div><h1>Overview</h1><div className="realm">Realm: {realm?.name ?? 'No realm'}</div></div>
          <div>
            {user.full_name} · <a className="logout" href={`${authUrl}/account`}>Account</a> · <a className="logout" href={`${authUrl}/logout`}>Sign out</a>
          </div>
        </div>
        <div className="cards">
          <section className="card"><span className="realm">Configured agents</span><strong>{agents.length}</strong></section>
          <section className="card"><span className="realm">Targets</span><strong>{targets.length}</strong></section>
          <section className="card"><span className="realm">Active alerts</span><strong>0</strong></section>
        </div>
        <section className="latency-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Last 24 hours</span>
              <h2>{icmpMonitor?.name ?? 'ICMP latency'}</h2>
            </div>
            <span className="realm">{points.length} observations · milliseconds</span>
          </div>
          <IcmpGraph points={points} />
        </section>
      </main>
    </div>
  )
}

type Agent = {id: string; name: string}
type Target = {id: string; name: string}
type Monitor = {id: string; name: string; probe_type: string}
