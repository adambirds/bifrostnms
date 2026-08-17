import Link from 'next/link'

import { TargetForm } from '@/app/targets/target-form'
import { authenticatedApiFetch } from '@/lib/auth'
import { headlineLabel, statusClass } from '@/lib/dashboard'
import type { Target, TargetOperationalSummary } from '@/lib/monitoring'

export default async function TargetsPage() {
  const [targets, summaries] = await Promise.all([
    authenticatedApiFetch<Target[]>('/monitoring/targets'),
    authenticatedApiFetch<TargetOperationalSummary[]>('/monitoring/dashboard/targets'),
  ])
  const summariesByTarget = new Map(summaries.map((summary) => [summary.target_id, summary]))

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Configuration and operations</span>
          <h1>Targets</h1>
          <p>Reusable destinations with an operational view across every configured monitor.</p>
        </div>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Add target</h2>
            <p className="muted">Monitor-specific ports and paths are configured later.</p>
          </div>
        </div>
        <TargetForm />
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Configured targets</h2>
          <span className="muted">{targets.length} total</span>
        </div>
        {targets.length ? (
          <div className="resource-table-wrap">
            <table className="resource-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Address</th>
                  <th>Operational state</th>
                  <th>Monitors</th>
                  <th>Description</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {targets.map((target) => {
                  const summary = summariesByTarget.get(target.id)
                  return (
                    <tr key={target.id}>
                      <td><Link href={`/targets/${target.id}`}><strong>{target.name}</strong></Link></td>
                      <td><code>{target.address}</code></td>
                      <td>
                        {summary ? <span className={statusClass(summary.headline)}>{headlineLabel(summary.headline)}</span> : <span className="status-muted">Unknown</span>}
                        {!target.enabled ? <div className="muted">Target disabled</div> : null}
                      </td>
                      <td>{summary?.monitor_count ?? 0}</td>
                      <td className="muted">{target.description ?? '—'}</td>
                      <td><Link className="secondary compact-action" href={`/targets/${target.id}`}>View</Link></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <strong>No targets yet</strong>
            <span>Create the first destination you want BifrostNMS to observe.</span>
          </div>
        )}
      </section>
    </>
  )
}
