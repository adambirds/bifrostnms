'use client'

import { useActionState } from 'react'

import {
  type MonitorAssignmentState,
  removeMonitorAgentAssignmentAction,
  removeMonitorAgentGroupAssignmentAction,
} from '@/app/monitors/assignment-actions'

type RemoveAssignmentButtonProps = {
  kind: 'agent' | 'group'
  monitorId: string
  resourceId: string
}

const initialMonitorAssignmentState: MonitorAssignmentState = {
  error: null,
  success: null,
}

export function RemoveAssignmentButton({
  kind,
  monitorId,
  resourceId,
}: RemoveAssignmentButtonProps) {
  const action =
    kind === 'agent'
      ? removeMonitorAgentAssignmentAction.bind(null, monitorId, resourceId)
      : removeMonitorAgentGroupAssignmentAction.bind(
          null,
          monitorId,
          resourceId,
        )
  const [state, formAction, pending] = useActionState(
    action,
    initialMonitorAssignmentState,
  )

  return (
    <form action={formAction} className="assignment-remove-form">
      <button type="submit" disabled={pending}>
        {pending ? 'Removing…' : 'Remove'}
      </button>
      {state.error ? <span className="form-error">{state.error}</span> : null}
    </form>
  )
}
