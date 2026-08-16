import assert from 'node:assert/strict'
import test from 'node:test'

import {
  availabilityLabel,
  headlineLabel,
  statusClass,
} from './dashboard.ts'

test('presents missing data and agent outage as distinct operator states', () => {
  assert.equal(availabilityLabel('overdue'), 'Missing data')
  assert.equal(availabilityLabel('agent_offline'), 'Agent offline')
  assert.notEqual(
    availabilityLabel('overdue'),
    availabilityLabel('agent_offline'),
  )
})

test('presents distributed disagreement as degraded rather than healthy', () => {
  assert.equal(headlineLabel('degraded'), 'Degraded')
  assert.equal(statusClass('degraded'), 'status-warning')
  assert.equal(statusClass('healthy'), 'status-ok')
  assert.equal(statusClass('unhealthy'), 'status-danger')
})
