'use client'

import { useActionState } from 'react'

import {
  createAgentGroupAction,
  createTargetGroupAction,
  initialGroupActionState,
} from '@/app/groups/actions'
import type { AgentGroup, TargetGroup } from '@/lib/monitoring'

type GroupFormProps =
  | { kind: 'agent'; groups: AgentGroup[] }
  | { kind: 'target'; groups: TargetGroup[] }

export function GroupForm({ kind, groups }: GroupFormProps) {
  const action = kind === 'agent' ? createAgentGroupAction : createTargetGroupAction
  const [state, formAction, pending] = useActionState(
    action,
    initialGroupActionState,
  )
  const label = kind === 'agent' ? 'agent' : 'target'

  return (
    <form className="resource-form" action={formAction}>
      <div className="form-grid">
        <label>
          Name
          <input name="name" required maxLength={200} />
        </label>
        <label>
          Parent group
          <select name="parent_id" defaultValue="">
            <option value="">No parent</option>
            {groups.map(group => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Description
        <textarea name="description" rows={2} />
      </label>
      {state.error ? <p className="form-error">{state.error}</p> : null}
      {state.success ? <p className="form-success">{state.success}</p> : null}
      <button type="submit" disabled={pending}>
        {pending ? 'Creating…' : `Create ${label} group`}
      </button>
    </form>
  )
}
