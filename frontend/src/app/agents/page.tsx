import { AgentForm } from '@/app/agents/agent-form'
import { EnrolmentControl } from '@/app/agents/enrolment-control'
import { authenticatedApiFetch } from '@/lib/auth'
import type { Agent, AgentStatus } from '@/lib/monitoring'

export default async function AgentsPage() {
  const agents = await authenticatedApiFetch<Agent[]>('/monitoring/agents')
  const statuses = await Promise.all(
    agents.map(agent =>
      authenticatedApiFetch<AgentStatus>(`/monitoring/agents/${agent.id}/status`),
    ),
  )
  const statusByAgent = new Map(statuses.map(status => [status.agent_id, status]))

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Monitoring locations</span>
          <h1>Agents</h1>
          <p>
            Distributed vantage points that execute probes and buffer results
            locally.
          </p>
        </div>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Add agent</h2>
            <p className="muted">
              Create the agent record before issuing its enrolment token.
            </p>
          </div>
        </div>
        <AgentForm />
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Configured agents</h2>
          <span className="muted">{agents.length} total</span>
        </div>
        {agents.length ? (
          <div className="resource-table-wrap">
            <table className="resource-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Connectivity</th>
                  <th>Host</th>
                  <th>Queue</th>
                  <th>Description</th>
                  <th>Enrolment</th>
                </tr>
              </thead>
              <tbody>
                {agents.map(agent => {
                  const status = statusByAgent.get(agent.id)
                  return (
                    <tr key={agent.id}>
                      <td>
                        <strong>{agent.name}</strong>
                      </td>
                      <td>
                        <span
                          className={
                            status?.online ? 'status-ok' : 'status-danger'
                          }
                        >
                          {status?.online ? 'Online' : 'Offline'}
                        </span>
                      </td>
                      <td className="muted">
                        {status?.hostname ?? 'Not enrolled'}
                      </td>
                      <td>{status?.queue_depth ?? 0}</td>
                      <td className="muted">{agent.description ?? '—'}</td>
                      <td>
                        <EnrolmentControl agentId={agent.id} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <strong>No agents yet</strong>
            <span>
              Create an agent for each network vantage point you want to monitor
              from.
            </span>
          </div>
        )}
      </section>
    </>
  )
}
