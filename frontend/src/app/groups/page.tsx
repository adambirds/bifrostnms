import { GroupForm } from '@/app/groups/group-form'
import { MembershipForm } from '@/app/groups/membership-form'
import { RemoveMembershipButton } from '@/app/groups/remove-membership-button'
import { authenticatedApiFetch } from '@/lib/auth'
import type {
  Agent,
  AgentGroup,
  AgentGroupMembership,
  Target,
  TargetGroup,
  TargetGroupMembership,
} from '@/lib/monitoring'

import './groups.css'

export default async function GroupsPage() {
  const [
    agentGroups,
    targetGroups,
    agents,
    targets,
    agentMemberships,
    targetMemberships,
  ] = await Promise.all([
    authenticatedApiFetch<AgentGroup[]>('/monitoring/agent-groups'),
    authenticatedApiFetch<TargetGroup[]>('/monitoring/target-groups'),
    authenticatedApiFetch<Agent[]>('/monitoring/agents'),
    authenticatedApiFetch<Target[]>('/monitoring/targets'),
    authenticatedApiFetch<AgentGroupMembership[]>(
      '/monitoring/agent-group-memberships',
    ),
    authenticatedApiFetch<TargetGroupMembership[]>(
      '/monitoring/target-group-memberships',
    ),
  ])

  const agentGroupNames = new Map(agentGroups.map(group => [group.id, group.name]))
  const targetGroupNames = new Map(targetGroups.map(group => [group.id, group.name]))
  const agentNames = new Map(agents.map(agent => [agent.id, agent.name]))
  const targetNames = new Map(targets.map(target => [target.id, target.name]))

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
                    <th>Members</th>
                    <th>Add agent</th>
                  </tr>
                </thead>
                <tbody>
                  {agentGroups.map(group => {
                    const memberships = agentMemberships.filter(
                      membership => membership.agent_group_id === group.id,
                    )
                    return (
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
                          {memberships.length ? (
                            <ul className="relationship-list">
                              {memberships.map(membership => (
                                <li key={membership.id}>
                                  <span>
                                    {agentNames.get(membership.agent_id) ??
                                      'Unknown agent'}
                                  </span>
                                  <RemoveMembershipButton
                                    kind="agent"
                                    groupId={group.id}
                                    resourceId={membership.agent_id}
                                  />
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <span className="muted">No members</span>
                          )}
                        </td>
                        <td>
                          <MembershipForm
                            kind="agent"
                            groupId={group.id}
                            resources={agents.filter(
                              agent =>
                                !memberships.some(
                                  membership => membership.agent_id === agent.id,
                                ),
                            )}
                          />
                        </td>
                      </tr>
                    )
                  })}
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
                    <th>Members</th>
                    <th>Add target</th>
                  </tr>
                </thead>
                <tbody>
                  {targetGroups.map(group => {
                    const memberships = targetMemberships.filter(
                      membership => membership.target_group_id === group.id,
                    )
                    return (
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
                          {memberships.length ? (
                            <ul className="relationship-list">
                              {memberships.map(membership => (
                                <li key={membership.id}>
                                  <span>
                                    {targetNames.get(membership.target_id) ??
                                      'Unknown target'}
                                  </span>
                                  <RemoveMembershipButton
                                    kind="target"
                                    groupId={group.id}
                                    resourceId={membership.target_id}
                                  />
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <span className="muted">No members</span>
                          )}
                        </td>
                        <td>
                          <MembershipForm
                            kind="target"
                            groupId={group.id}
                            resources={targets.filter(
                              target =>
                                !memberships.some(
                                  membership => membership.target_id === target.id,
                                ),
                            )}
                          />
                        </td>
                      </tr>
                    )
                  })}
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
