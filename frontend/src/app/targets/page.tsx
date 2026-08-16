import {TargetForm} from '@/app/targets/target-form'
import {authenticatedApiFetch} from '@/lib/auth'
import type {Target} from '@/lib/monitoring'

export default async function TargetsPage() {
  const targets = await authenticatedApiFetch<Target[]>('/monitoring/targets')

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Configuration</span>
          <h1>Targets</h1>
          <p>Reusable destinations monitored from one or more agents.</p>
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
                  <th>Status</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {targets.map(target => (
                  <tr key={target.id}>
                    <td><strong>{target.name}</strong></td>
                    <td><code>{target.address}</code></td>
                    <td><span className={target.enabled ? 'status-ok' : 'status-muted'}>{target.enabled ? 'Enabled' : 'Disabled'}</span></td>
                    <td className="muted">{target.description ?? '—'}</td>
                  </tr>
                ))}
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
