'use client'

import { useActionState } from 'react'

import {
  initialMonitorEditState,
  updateMonitorAction,
} from '@/app/monitors/edit-actions'
import { MonitorFields } from '@/app/monitors/monitor-fields'
import type { Monitor, Target } from '@/lib/monitoring'

export function EditMonitorForm({
  monitor,
  targets,
}: {
  monitor: Monitor
  targets: Target[]
}) {
  const action = updateMonitorAction.bind(null, monitor.id)
  const [state, formAction, pending] = useActionState(
    action,
    initialMonitorEditState,
  )

  return (
    <form className="resource-form" action={formAction}>
      <MonitorFields targets={targets} monitor={monitor} />
      <p className="muted">
        Behavioral changes create a new monitor revision and are distributed to
        assigned agents through their next desired-configuration update.
      </p>
      {state.error ? <p className="form-error">{state.error}</p> : null}
      {state.success ? <p className="form-success">{state.success}</p> : null}
      <button type="submit" disabled={pending || targets.length === 0}>
        {pending ? 'Saving…' : 'Save changes'}
      </button>
    </form>
  )
}
