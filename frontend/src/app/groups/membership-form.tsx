'use client'

import { useActionState } from 'react'

import {
  addAgentGroupMembershipAction,
  addTargetGroupMembershipAction,
  type GroupActionState,
} from '@/app/groups/actions'
import type { Agent, Target } from '@/lib/monitoring'

const initialGroupActionState: GroupActionState = {
  error: null,
  success: null,
}

type MembershipFormProps =
  | { kind: 'agent'; groupId: string; resources: Agent[] }
  | { kind: 'target'; groupId: string; resources: Target[] }

export function MembershipForm(props: MembershipFormProps) {
  const action =
    props.kind === 'agent'
      ? addAgentGroupMembershipAction.bind(null, props.groupId)
      : addTargetGroupMembershipAction.bind(null, props.groupId)
  const [state, formAction, pending] = useActionState(
    action,
    initialGroupActionState,
  )
  const fieldName = props.kind === 'agent' ? 'agent_id' : 'target_id'
  const label = props.kind === 'agent' ? 'agent' : 'target'

  return (
    <form className="membership-form" action={formAction}>
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
        {pending ? 'Adding…' : 'Add'}
      </button>
      {state.error ? <span className="form-error">{state.error}</span> : null}
      {state.success ? (
        <span className="form-success">{state.success}</span>
      ) : null}
    </form>
  )
}
