import Link from 'next/link'

import { AssignmentForm } from '@/app/monitors/assignment-form'
import { BulkMonitorForm } from '@/app/monitors/bulk-monitor-form'
import { MonitorForm } from '@/app/monitors/monitor-form'
import { authenticatedApiFetch } from '@/lib/auth'
import type {
  Agent,
  AgentGroup,
  Monitor,
  MonitorAgentAssignment,
  MonitorAgentGroupAssignment,
  Target,
  TargetGroup,
} from '@/lib/monitoring'

import './monitors.css'

type MonitorsPageProps = {
  searchParams: Promise<{ duplicate?: string }>
}

export default async function MonitorsPage({ searchParams }: MonitorsPageProps) {
  const { duplicate } = await searchParams
  const [
    monitors,
    targets,
    targetGroups,
    agents,
    agentGroups,
    directAssignments,
    groupAssignments,
  ] = await Promise.all([
    authenticatedApiFetch<Monitor[]>('/monitoring/monitors'),
    authenticatedApiFetch<Target[]>('/monitoring/targets'),
    authenticatedApiFetch<TargetGroup[]>('/monitoring/target-groups'),
    authenticatedApiFetch<Agent[]>('/monitoring/agents'),
    authenticatedApiFetch<AgentGroup[]>('/monitoring/agent-groups'),
    authenticatedApiFetch<MonitorAgentAssignment[]>(
      '/monitoring/monitor-agent-assignments',
    ),
    authenticatedApiFetch<MonitorAgentGroupAssignment[]>(
      '/monitoring/monitor-agent-group-assignments',
    ),
  ])
  const targetNames = new Map(targets.map((target) => [target.id, target.name]))
  const agentNames = new Map(agents.map((agent) => [agent.id, agent.name]))
  const groupNames = new Map(agentGroups.map((group) => [group.id, group.name]))

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

      <section className="panel" id="bulk-create">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Configure once, apply broadly</span>
            <h2>Bulk create or duplicate monitors</h2>
            <p className="muted">
              Apply a shared probe definition to a target group or selected targets.
              BifrostNMS still creates explicit per-target monitors so history and
              revisions remain independently traceable.
            </p>
          </div>
        </div>
        <BulkMonitorForm
          targets={targets}
          targetGroups={targetGroups}
          monitors={monitors}
          agents={agents}
          agentGroups={agentGroups}
          initialSourceMonitorId={duplicate}
        />
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Create one monitor</h2>
            <p className="muted">
              Use this for target-specific checks such as web paths, assertions or
              ports that are not shared across the estate.
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
                  <th>Assignments</th>
                  <th>Manage</th>
                </tr>
              </thead>
              <tbody>
                {monitors.map((monitor) => {
                  const monitorDirectAssignments = directAssignments.filter(
                    (assignment) => assignment.monitor_id === monitor.id,
                  )
                  const monitorGroupAssignments = groupAssignments.filter(
                    (assignment) => assignment.monitor_id === monitor.id,
                  )
                  const availableAgents = agents.filter(
                    (agent) =>
                      !monitorDirectAssignments.some(
                        (assignment) => assignment.agent_id === agent.id,
                      ),
                  )
                  const availableGroups = agentGroups.filter(
                    (group) =>
                      !monitorGroupAssignments.some(
                        (assignment) => assignment.agent_group_id === group.id,
                      ),
                  )

                  return (
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
                        <div className="assignment-management">
                          <div>
                            <strong>Agents</strong>
                            {monitorDirectAssignments.length ? (
                              <ul className="compact-list">
                                {monitorDirectAssignments.map((assignment) => (
                                  <li key={assignment.id}>
                                    {agentNames.get(assignment.agent_id) ??
                                      'Unknown agent'}
                                    <AssignmentForm
                                      kind="remove-agent"
                                      monitorId={monitor.id}
                                      resourceId={assignment.agent_id}
                                    />
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <span className="muted">None</span>
                            )}
                            <AssignmentForm
                              kind="agent"
                              monitorId={monitor.id}
                              resources={availableAgents}
                            />
                          </div>
                          <div>
                            <strong>Agent groups</strong>
                            {monitorGroupAssignments.length ? (
                              <ul className="compact-list">
                                {monitorGroupAssignments.map((assignment) => (
                                  <li key={assignment.id}>
                                    {groupNames.get(assignment.agent_group_id) ??
                                      'Unknown group'}
                                    <AssignmentForm
                                      kind="remove-group"
                                      monitorId={monitor.id}
                                      resourceId={assignment.agent_group_id}
                                    />
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <span className="muted">None</span>
                            )}
                            <AssignmentForm
                              kind="group"
                              monitorId={monitor.id}
                              resources={availableGroups}
                            />
                          </div>
                        </div>
                      </td>
                      <td>
                        <div className="page-actions">
                          <Link
                            className="secondary compact-action"
                            href={`/monitors/${monitor.id}`}
                          >
                            View
                          </Link>
                          <Link
                            className="secondary compact-action"
                            href={`/monitors/${monitor.id}/edit`}
                          >
                            Edit
                          </Link>
                          <Link
                            className="secondary compact-action"
                            href={`/monitors?duplicate=${monitor.id}#bulk-create`}
                          >
                            Duplicate
                          </Link>
                        </div>
                      </td>
                    </tr>
                  )
                })}
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
