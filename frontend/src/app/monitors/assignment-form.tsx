'use client'

import { useActionState } from 'react'

import {
  assignMonitorToAgentAction,
  assignMonitorToAgentGroupAction,
  initialMonitorAssignmentState,
} from '@/app/monitors/assignment-actions'
import type { Agent, AgentGroup } from '@/lib/monitoring'

type AssignmentFormProps =
  | { kind: 'agent'; monitorId: string; resources: Agent[] }
  | { kind: 'group'; monitorId: string; resources: AgentGroup[] }

export function AssignmentForm(props: AssignmentFormProps) {
  const action =
    props.kind === 'agent'
      ? assignMonitorToAgentAction.bind(null, props.monitorId)
      : assignMonitorToAgentGroupAction.bind(null, props.monitorId)
  const [state, formAction, pending] = useActionState(
    action,
    initialMonitorAssignmentState,
  )
  const fieldName = props.kind === 'agent' ? 'agent_id' : 'agent_group_id'
  const label = props.kind === 'agent' ? 'agent' : 'agent group'

  return (
    <form className="assignment-form" action={formAction}>
      <select name={fieldName} defaultValue="" required>
        <option value="" disabled>
          Select {label}
        </option>
        {props.resources.map(resource => (
          <option key={resource.id} value={resource.id}>
            {resource.name}
          </option>
        ))}
      </select>
      <button type="submit" disabled={pending || props.resources.length === 0}>
        {pending ? 'Assigning…' : 'Assign'}
      </button>
      {state.error ? <span className="form-error">{state.error}</span> : null}
      {state.success ? (
        <span className="form-success">{state.success}</span>
      ) : null}
    </form>
  )
}
