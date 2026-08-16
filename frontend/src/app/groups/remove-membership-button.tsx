'use client'

import { useActionState } from 'react'

import {
  initialGroupActionState,
  removeAgentGroupMembershipAction,
  removeTargetGroupMembershipAction,
} from '@/app/groups/actions'

type RemoveMembershipButtonProps = {
  kind: 'agent' | 'target'
  groupId: string
  resourceId: string
}

export function RemoveMembershipButton({
  kind,
  groupId,
  resourceId,
}: RemoveMembershipButtonProps) {
  const action =
    kind === 'agent'
      ? removeAgentGroupMembershipAction.bind(null, groupId, resourceId)
      : removeTargetGroupMembershipAction.bind(null, groupId, resourceId)
  const [state, formAction, pending] = useActionState(
    action,
    initialGroupActionState,
  )

  return (
    <form action={formAction} className="relationship-remove-form">
      <button type="submit" disabled={pending}>
        {pending ? 'Removing…' : 'Remove'}
      </button>
      {state.error ? <span className="form-error">{state.error}</span> : null}
    </form>
  )
}
