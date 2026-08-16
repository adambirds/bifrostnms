import { AssignmentForm } from '@/app/monitors/assignment-form'
import { MonitorForm } from '@/app/monitors/monitor-form'
import { authenticatedApiFetch } from '@/lib/auth'
import type {
  Agent,
  AgentGroup,
  Monitor,
  Target,
} from '@/lib/monitoring'

import './monitors.css'

export default async function MonitorsPage() {
  const [monitors, targets, agents, agentGroups] = await Promise.all([
    authenticatedApiFetch<Monitor[]>('/monitoring/monitors'),
    authenticatedApiFetch<Target[]>('/monitoring/targets'),
    authenticatedApiFetch<Agent[]>('/monitoring/agents'),
    authenticatedApiFetch<AgentGroup[]>('/monitoring/agent-groups'),
  ])
  const targetNames = new Map(targets.map(target => [target.id, target.name]))

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Checks</span>
          <h1>Monitors</h1>
          <p>
            Define what BifrostNMS should probe, how often it should run and what
            the result should be assessed against.
          </p>
        </div>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Create monitor</h2>
            <p className="muted">
              Probe configuration is validated by the same typed control-plane
              contracts distributed to agents.
            </p>
          </div>
        </div>
        <MonitorForm targets={targets} />
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>Configured monitors</h2>
          <span className="muted">{monitors.length} total</span>
        </div>
        {monitors.length ? (
          <div className="resource-table-wrap">
            <table className="resource-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Target</th>
                  <th>Probe</th>
                  <th>Schedule</th>
                  <th>Revision</th>
                  <th>Status</th>
                  <th>Assign agent</th>
                  <th>Assign group</th>
                </tr>
              </thead>
              <tbody>
                {monitors.map(monitor => (
                  <tr key={monitor.id}>
                    <td>
                      <strong>{monitor.name}</strong>
                      {monitor.description ? (
                        <div className="muted">{monitor.description}</div>
                      ) : null}
                    </td>
                    <td>
                      {targetNames.get(monitor.target_id) ?? 'Unknown target'}
                    </td>
                    <td>
                      <code>{monitor.probe_type.toUpperCase()}</code>
                    </td>
                    <td className="muted">
                      Every {monitor.interval_seconds}s · {monitor.timeout_seconds}s
                      {' timeout'}
                    </td>
                    <td>{monitor.revision}</td>
                    <td>
                      <span
                        className={monitor.enabled ? 'status-ok' : 'status-muted'}
                      >
                        {monitor.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </td>
                    <td>
                      <AssignmentForm
                        kind="agent"
                        monitorId={monitor.id}
                        resources={agents}
                      />
                    </td>
                    <td>
                      <AssignmentForm
                        kind="group"
                        monitorId={monitor.id}
                        resources={agentGroups}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <strong>No monitors yet</strong>
            <span>
              Create a target first, then define the probe that should run against
              it.
            </span>
          </div>
        )}
      </section>
    </>
  )
}
