import { GroupForm } from '@/app/groups/group-form'
import { MembershipForm } from '@/app/groups/membership-form'
import { authenticatedApiFetch } from '@/lib/auth'
import type {
  Agent,
  AgentGroup,
  Target,
  TargetGroup,
} from '@/lib/monitoring'

import './groups.css'

export default async function GroupsPage() {
  const [agentGroups, targetGroups, agents, targets] = await Promise.all([
    authenticatedApiFetch<AgentGroup[]>('/monitoring/agent-groups'),
    authenticatedApiFetch<TargetGroup[]>('/monitoring/target-groups'),
    authenticatedApiFetch<Agent[]>('/monitoring/agents'),
    authenticatedApiFetch<Target[]>('/monitoring/targets'),
  ])

  const agentGroupNames = new Map(agentGroups.map(group => [group.id, group.name]))
  const targetGroupNames = new Map(targetGroups.map(group => [group.id, group.name]))

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Organisation</span>
          <h1>Groups</h1>
          <p>
            Organise agents and targets into reusable hierarchies for assignments
            and navigation.
          </p>
        </div>
      </div>

      <div className="group-columns">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Agent groups</h2>
              <p className="muted">
                Group monitoring locations so monitors can be assigned once to
                multiple agents.
              </p>
            </div>
          </div>
          <GroupForm kind="agent" groups={agentGroups} />

          {agentGroups.length ? (
            <div className="resource-table-wrap">
              <table className="resource-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Parent</th>
                    <th>Status</th>
                    <th>Add agent</th>
                  </tr>
                </thead>
                <tbody>
                  {agentGroups.map(group => (
                    <tr key={group.id}>
                      <td>
                        <strong>{group.name}</strong>
                        {group.description ? (
                          <div className="muted">{group.description}</div>
                        ) : null}
                      </td>
                      <td className="muted">
                        {group.parent_id
                          ? (agentGroupNames.get(group.parent_id) ?? 'Unknown')
                          : 'Root'}
                      </td>
                      <td>
                        <span
                          className={group.enabled ? 'status-ok' : 'status-muted'}
                        >
                          {group.enabled ? 'Enabled' : 'Disabled'}
                        </span>
                      </td>
                      <td>
                        <MembershipForm
                          kind="agent"
                          groupId={group.id}
                          resources={agents}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              <strong>No agent groups yet</strong>
              <span>Create a group to organise monitoring locations.</span>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Target groups</h2>
              <p className="muted">
                Build target hierarchies for sites, services, environments or
                other operational boundaries.
              </p>
            </div>
          </div>
          <GroupForm kind="target" groups={targetGroups} />

          {targetGroups.length ? (
            <div className="resource-table-wrap">
              <table className="resource-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Parent</th>
                    <th>Add target</th>
                  </tr>
                </thead>
                <tbody>
                  {targetGroups.map(group => (
                    <tr key={group.id}>
                      <td>
                        <strong>{group.name}</strong>
                        {group.description ? (
                          <div className="muted">{group.description}</div>
                        ) : null}
                      </td>
                      <td className="muted">
                        {group.parent_id
                          ? (targetGroupNames.get(group.parent_id) ?? 'Unknown')
                          : 'Root'}
                      </td>
                      <td>
                        <MembershipForm
                          kind="target"
                          groupId={group.id}
                          resources={targets}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              <strong>No target groups yet</strong>
              <span>Create a group to organise monitored targets.</span>
            </div>
          )}
        </section>
      </div>
    </>
  )
}
