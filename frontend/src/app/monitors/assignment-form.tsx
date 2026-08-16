'use client'

import { useActionState } from 'react'

import {
  assignMonitorToAgentAction,
  assignMonitorToAgentGroupAction,
  type MonitorAssignmentState,
  removeMonitorAgentAssignmentAction,
  removeMonitorAgentGroupAssignmentAction,
} from '@/app/monitors/assignment-actions'
import type { Agent, AgentGroup } from '@/lib/monitoring'

const initialMonitorAssignmentState: MonitorAssignmentState = {
  error: null,
  success: null,
}

type AssignmentFormProps =
  | { kind: 'agent'; monitorId: string; resources: Agent[] }
  | { kind: 'group'; monitorId: string; resources: AgentGroup[] }
  | { kind: 'remove-agent'; monitorId: string; resourceId: string }
  | { kind: 'remove-group'; monitorId: string; resourceId: string }

export function AssignmentForm(props: AssignmentFormProps) {
  const action = (() => {
    switch (props.kind) {
      case 'agent':
        return assignMonitorToAgentAction.bind(null, props.monitorId)
      case 'group':
        return assignMonitorToAgentGroupAction.bind(null, props.monitorId)
      case 'remove-agent':
        return removeMonitorAgentAssignmentAction.bind(
          null,
          props.monitorId,
          props.resourceId,
        )
      case 'remove-group':
        return removeMonitorAgentGroupAssignmentAction.bind(
          null,
          props.monitorId,
          props.resourceId,
        )
    }
  })()
  const [state, formAction, pending] = useActionState(
    action,
    initialMonitorAssignmentState,
  )

  if (props.kind === 'remove-agent' || props.kind === 'remove-group') {
    return (
      <form className="assignment-remove-form" action={formAction}>
        <button type="submit" disabled={pending}>
          {pending ? 'Removing…' : 'Remove'}
        </button>
        {state.error ? <span className="form-error">{state.error}</span> : null}
      </form>
    )
  }

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
