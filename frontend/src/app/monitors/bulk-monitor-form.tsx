'use client'

import { useActionState, useState } from 'react'

import {
  createBulkMonitorsAction,
  type BulkMonitorFormState,
} from '@/app/monitors/bulk-actions'
import { MonitorFields } from '@/app/monitors/monitor-fields'
import type {
  Agent,
  AgentGroup,
  Monitor,
  Target,
  TargetGroup,
} from '@/lib/monitoring'

const initialState: BulkMonitorFormState = {
  error: null,
  success: null,
}

export function BulkMonitorForm({
  targets,
  targetGroups,
  monitors,
  agents,
  agentGroups,
  initialSourceMonitorId,
}: {
  targets: Target[]
  targetGroups: TargetGroup[]
  monitors: Monitor[]
  agents: Agent[]
  agentGroups: AgentGroup[]
  initialSourceMonitorId?: string
}) {
  const [state, formAction, pending] = useActionState(
    createBulkMonitorsAction,
    initialState,
  )
  const hasInitialSource = monitors.some(
    (monitor) => monitor.id === initialSourceMonitorId,
  )
  const [definitionMode, setDefinitionMode] = useState<'new' | 'copy'>(
    hasInitialSource ? 'copy' : 'new',
  )
  const [targetMode, setTargetMode] = useState<'group' | 'selected'>('group')

  return (
    <form className="resource-form bulk-monitor-form" action={formAction}>
      <div className="bulk-monitor-options">
        <fieldset>
          <legend>Definition</legend>
          <label className="checkbox-label">
            <input
              type="radio"
              name="definition_mode"
              value="new"
              checked={definitionMode === 'new'}
              onChange={() => setDefinitionMode('new')}
            />
            Create a new shared definition
          </label>
          <label className="checkbox-label">
            <input
              type="radio"
              name="definition_mode"
              value="copy"
              checked={definitionMode === 'copy'}
              onChange={() => setDefinitionMode('copy')}
            />
            Duplicate an existing monitor
          </label>
        </fieldset>

        <fieldset>
          <legend>Targets</legend>
          <label className="checkbox-label">
            <input
              type="radio"
              name="target_mode"
              value="group"
              checked={targetMode === 'group'}
              onChange={() => setTargetMode('group')}
            />
            Target group
          </label>
          <label className="checkbox-label">
            <input
              type="radio"
              name="target_mode"
              value="selected"
              checked={targetMode === 'selected'}
              onChange={() => setTargetMode('selected')}
            />
            Selected targets
          </label>
        </fieldset>
      </div>

      {targetMode === 'group' ? (
        <label>
          Target group
          <select name="target_group_id" defaultValue="" required>
            <option value="" disabled>
              Select target group
            </option>
            {targetGroups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <label>
          Targets
          <select name="target_ids" multiple size={Math.min(10, Math.max(4, targets.length))}>
            {targets.map((target) => (
              <option key={target.id} value={target.id}>
                {target.name} — {target.address}
              </option>
            ))}
          </select>
          <span className="muted">Use Ctrl/Cmd or Shift to select multiple targets.</span>
        </label>
      )}

      {definitionMode === 'copy' ? (
        <div className="form-grid">
          <label>
            Source monitor
            <select
              name="source_monitor_id"
              defaultValue={hasInitialSource ? initialSourceMonitorId : ''}
              required
            >
              <option value="" disabled>
                Select monitor
              </option>
              {monitors.map((monitor) => (
                <option key={monitor.id} value={monitor.id}>
                  {monitor.name} ({monitor.probe_type.toUpperCase()})
                </option>
              ))}
            </select>
          </label>
          <label>
            Name template
            <input
              name="name_template"
              defaultValue="{target} - {source}"
              maxLength={200}
              required
            />
          </label>
        </div>
      ) : (
        <MonitorFields
          targets={[]}
          includeTarget={false}
          nameField="name_template"
          nameLabel="Name template"
          defaultName="{target} - {probe}"
        />
      )}

      <div className="bulk-monitor-assignments">
        <div>
          <strong>Run from agents</strong>
          {agents.length ? (
            <div className="bulk-checkbox-grid">
              {agents.map((agent) => (
                <label className="checkbox-label" key={agent.id}>
                  <input type="checkbox" name="agent_ids" value={agent.id} />
                  {agent.name}
                </label>
              ))}
            </div>
          ) : (
            <span className="muted">No agents available.</span>
          )}
        </div>
        <div>
          <strong>Run from agent groups</strong>
          {agentGroups.length ? (
            <div className="bulk-checkbox-grid">
              {agentGroups.map((group) => (
                <label className="checkbox-label" key={group.id}>
                  <input
                    type="checkbox"
                    name="agent_group_ids"
                    value={group.id}
                  />
                  {group.name}
                </label>
              ))}
            </div>
          ) : (
            <span className="muted">No agent groups available.</span>
          )}
        </div>
      </div>

      <label className="checkbox-label">
        <input name="skip_existing" type="checkbox" defaultChecked />
        Skip targets that already have an equivalent monitor
      </label>

      <p className="muted">
        Supported name tokens: <code>{'{target}'}</code>,{' '}
        <code>{'{address}'}</code>, <code>{'{probe}'}</code> and{' '}
        <code>{'{source}'}</code> when duplicating.
      </p>

      {state.error ? <p className="form-error">{state.error}</p> : null}
      {state.success ? <p className="form-success">{state.success}</p> : null}
      <button
        type="submit"
        disabled={
          pending ||
          targets.length === 0 ||
          (targetMode === 'group' && targetGroups.length === 0) ||
          (definitionMode === 'copy' && monitors.length === 0)
        }
      >
        {pending ? 'Creating monitors…' : 'Create monitors in bulk'}
      </button>
    </form>
  )
}
