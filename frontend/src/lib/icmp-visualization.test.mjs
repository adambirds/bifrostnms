import assert from 'node:assert/strict'
import test from 'node:test'

import { buildIcmpSeries, graphTimeBounds } from './icmp-visualization.ts'

const point = (agentId, scheduledAt, median = 10) => ({
  scheduled_at: scheduledAt,
  agent_id: agentId,
  packet_loss_percent: 0,
  min_rtt_ms: median - 1,
  median_rtt_ms: median,
  max_rtt_ms: median + 1,
  rtt_samples_ms: [median - 1, median, median + 1],
})

test('keeps agent series independent for cross-agent comparison', () => {
  const series = buildIcmpSeries(
    [
      point('agent-b', '2026-08-16T12:00:00Z'),
      point('agent-a', '2026-08-16T12:00:00Z'),
      point('agent-a', '2026-08-16T12:01:00Z'),
      point('agent-b', '2026-08-16T12:01:00Z'),
    ],
    60,
  )

  assert.deepEqual(
    series.map((item) => item.agentId),
    ['agent-a', 'agent-b'],
  )
  assert.equal(series[0].segments[0].length, 2)
  assert.equal(series[1].segments[0].length, 2)
})

test('splits lines across missing observations instead of fabricating continuity', () => {
  const series = buildIcmpSeries(
    [
      point('agent-a', '2026-08-16T12:00:00Z'),
      point('agent-a', '2026-08-16T12:01:00Z'),
      point('agent-a', '2026-08-16T12:06:00Z'),
    ],
    60,
  )

  assert.equal(series[0].segments.length, 2)
  assert.equal(series[0].segments[0].length, 2)
  assert.equal(series[0].segments[1].length, 1)
})

test('uses observation timestamps for graph bounds', () => {
  const bounds = graphTimeBounds([
    point('agent-a', '2026-08-16T12:02:00Z'),
    point('agent-a', '2026-08-16T12:00:00Z'),
  ])

  assert.equal(bounds?.startMs, Date.parse('2026-08-16T12:00:00Z'))
  assert.equal(bounds?.endMs, Date.parse('2026-08-16T12:02:00Z'))
})
