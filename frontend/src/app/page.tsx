import {requireUser} from '@/lib/auth'

export default async function DashboardPage() {
  const user = await requireUser()
  const realm = user.realms.find(r => r.id === user.active_realm_id) ?? user.realms[0]

  return (
    <div className="shell">
      <aside>
        <div className="brand">BifrostNMS</div>
        <nav><a href="/">Overview</a><a href="#">Targets</a><a href="#">Agents</a><a href="#">Monitors</a><a href="#">Alerts</a><a href="#">Settings</a></nav>
      </aside>
      <main>
        <div className="top">
          <div><h1>Overview</h1><div className="realm">Realm: {realm?.name ?? 'No realm'}</div></div>
          <div>{user.full_name} · <a className="logout" href="http://localhost:3001/logout">Sign out</a></div>
        </div>
        <div className="cards">
          <section className="card"><span className="realm">Agents online</span><strong>0</strong></section>
          <section className="card"><span className="realm">Targets</span><strong>0</strong></section>
          <section className="card"><span className="realm">Active alerts</span><strong>0</strong></section>
        </div>
      </main>
    </div>
  )
}
