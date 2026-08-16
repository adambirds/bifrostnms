'use client'

import { useActionState } from 'react'

import {
  createMonitorAction,
  initialMonitorFormState,
} from '@/app/monitors/actions'
import { MonitorFields } from '@/app/monitors/monitor-fields'
import type { Target } from '@/lib/monitoring'

export function MonitorForm({ targets }: { targets: Target[] }) {
  const [state, formAction, pending] = useActionState(
    createMonitorAction,
    initialMonitorFormState,
  )

  return (
    <form className="resource-form" action={formAction}>
      <MonitorFields targets={targets} />
      {state.error ? <p className="form-error">{state.error}</p> : null}
      {state.success ? <p className="form-success">{state.success}</p> : null}
      <button type="submit" disabled={pending || targets.length === 0}>
        {pending ? 'Creating…' : 'Create monitor'}
      </button>
    </form>
  )
}
