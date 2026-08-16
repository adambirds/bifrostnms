'use client'

import { useMemo, useState, type CSSProperties } from 'react'

import {
  buildIcmpSeries,
  type IcmpVisualizationPoint,
} from '@/lib/icmp-visualization'

export type IcmpPoint = IcmpVisualizationPoint & {
  packets_sent: number
  packets_received: number
  avg_rtt_ms: number | null
  p95_rtt_ms: number | null
  jitter_ms: number | null
}

export type IcmpObservationMeta = {
  scheduled_at: string
  agent_id: string
  execution_status: 'completed' | 'failed'
  assessment: 'healthy' | 'unhealthy' | 'unknown'
}

type IcmpGraphProps = {
  points: IcmpPoint[]
  observations: IcmpObservationMeta[]
  intervalSeconds: number
  rangeStart: string
  rangeEnd: string
  agentNames?: Record<string, string>
}

type AgentSummary = {
  agentId: string
  name: string
  latest: IcmpPoint | null
  averageRtt: number | null
  averageP95: number | null
  averageLoss: number
  latestJitter: number | null
  samples: number
  availability: number
  assessment: IcmpObservationMeta['assessment']
  sparkline: IcmpPoint[]
}

const width = 1200
const height = 390
const left = 72
const right = 24
const top = 24
const plotBottom = 270
const lossTop = 326
const lossHeight = 18
const seriesClasses = [
  'series-0',
  'series-1',
  'series-2',
  'series-3',
  'series-4',
  'series-5',
]

function finite(values: Array<number | null | undefined>): number[] {
  return values.filter((value): value is number => value !== null && value !== undefined)
}

function average(values: number[]): number | null {
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function percentile(values: number[], fraction: number): number | null {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  const position = (sorted.length - 1) * fraction
  const lower = Math.floor(position)
  const upper = Math.ceil(position)
  if (lower === upper) return sorted[lower]
  const weight = position - lower
  return sorted[lower] + (sorted[upper] - sorted[lower]) * weight
}

function formatMs(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(value >= 100 ? 0 : 1)} ms`
}

function formatPercent(value: number): string {
  return `${value.toFixed(value >= 10 ? 0 : 1)}%`
}

function formatTick(timestamp: number, durationMs: number): string[] {
  const date = new Date(timestamp)
  if (durationMs <= 24 * 60 * 60 * 1000) {
    return [
      new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(date),
    ]
  }
  if (durationMs <= 7 * 24 * 60 * 60 * 1000) {
    return [
      new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric' }).format(date),
      new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(date),
    ]
  }
  return [new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' }).format(date)]
}

function lossClass(value: number): string {
  if (value <= 0) return 'loss-none'
  if (value <= 1) return 'loss-trace'
  if (value <= 5) return 'loss-low'
  if (value <= 20) return 'loss-medium'
  return 'loss-high'
}

function latestByTime<T extends { scheduled_at: string }>(items: T[]): T | null {
  if (!items.length) return null
  return [...items].sort(
    (a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime(),
  )[0]
}

function Sparkline({ points }: { points: IcmpPoint[] }) {
  const values = finite(points.map((point) => point.median_rtt_ms))
  if (values.length < 2) return <span className="sparkline-empty">—</span>
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const spread = Math.max(maximum - minimum, 1)
  const polyline = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * 110
      const y = 24 - ((value - minimum) / spread) * 20
      return `${x},${y}`
    })
    .join(' ')
  return (
    <svg aria-hidden="true" className="agent-sparkline" viewBox="0 0 110 28">
      <polyline points={polyline} />
    </svg>
  )
}

export function IcmpGraph({
  points,
  observations,
  intervalSeconds,
  rangeStart,
  rangeEnd,
  agentNames = {},
}: IcmpGraphProps) {
  const [hovered, setHovered] = useState<IcmpPoint | null>(null)
  const startMs = new Date(rangeStart).getTime()
  const endMs = new Date(rangeEnd).getTime()
  const durationMs = Math.max(endMs - startMs, 1)
  const allSamples = useMemo(() => points.flatMap((point) => point.rtt_samples_ms), [points])
  const p99 = percentile(allSamples, 0.99) ?? 1
  const absoluteMax = Math.max(1, ...allSamples)
  const yMaximum = Math.max(10, Math.ceil(Math.min(absoluteMax, p99 * 1.25) / 5) * 5)
  const plotWidth = width - left - right
  const plotHeight = plotBottom - top
  const x = (scheduledAt: string) =>
    left + ((new Date(scheduledAt).getTime() - startMs) / durationMs) * plotWidth
  const y = (value: number) =>
    top + plotHeight - (Math.min(value, yMaximum) / yMaximum) * plotHeight
  const series = useMemo(() => buildIcmpSeries(points, intervalSeconds), [points, intervalSeconds])
  const observationWidth = Math.max(
    1.25,
    Math.min(7, (intervalSeconds * 1000 * plotWidth) / durationMs),
  )
  const smokeWidth = Math.max(2.4, observationWidth * 1.65)
  const timeTicks = Array.from({ length: 7 }, (_, index) => startMs + (durationMs * index) / 6)
  const yTicks = Array.from({ length: 5 }, (_, index) => (yMaximum * index) / 4).reverse()
  const latest = latestByTime(points)
  const losses = points.map((point) => point.packet_loss_percent)
  const currentLoss = latest?.packet_loss_percent ?? 0
  const minimumLoss = losses.length ? Math.min(...losses) : 0
  const averageLoss = average(losses) ?? 0
  const maximumLoss = Math.max(0, ...losses)
  const jitterValues = finite(points.map((point) => point.jitter_ms))
  const completed = observations.filter(
    (observation) => observation.execution_status === 'completed',
  ).length
  const failed = observations.filter(
    (observation) => observation.execution_status === 'failed',
  ).length
  const availability = observations.length ? (completed / observations.length) * 100 : 0

  const agentSummaries: AgentSummary[] = [...new Set(observations.map((item) => item.agent_id))]
    .map((agentId) => {
      const agentPoints = points.filter((point) => point.agent_id === agentId)
      const agentObservations = observations.filter((item) => item.agent_id === agentId)
      const agentLatestObservation = latestByTime(agentObservations)
      const agentSamples = agentPoints.flatMap((point) => point.rtt_samples_ms)
      return {
        agentId,
        name: agentNames[agentId] ?? agentId,
        latest: latestByTime(agentPoints),
        averageRtt: average(agentSamples),
        averageP95: average(finite(agentPoints.map((point) => point.p95_rtt_ms))),
        averageLoss: average(agentPoints.map((point) => point.packet_loss_percent)) ?? 0,
        latestJitter: latestByTime(agentPoints)?.jitter_ms ?? null,
        samples: agentSamples.length,
        availability: agentObservations.length
          ? (agentObservations.filter((item) => item.execution_status === 'completed').length /
              agentObservations.length) *
            100
          : 0,
        assessment: agentLatestObservation?.assessment ?? 'unknown',
        sparkline: [...agentPoints]
          .sort(
            (a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime(),
          )
          .slice(-48),
      }
    })
    .sort((a, b) => a.name.localeCompare(b.name))

  if (points.length === 0) {
    return (
      <div className="empty-graph">
        No successful ICMP measurements in this time range. Missing measurements are shown
        as gaps rather than zero latency.
      </div>
    )
  }

  return (
    <div className="smokeping-dashboard">
      <div className="historical-chart-card">
        <div className="chart-title-row">
          <div>
            <span className="eyebrow">Historical latency</span>
            <strong>
              {new Intl.DateTimeFormat(undefined, {
                day: 'numeric',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
              }).format(new Date(startMs))}{' '}
              –{' '}
              {new Intl.DateTimeFormat(undefined, {
                day: 'numeric',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
              }).format(new Date(endMs))}
            </strong>
          </div>
          <div className="modern-graph-legend">
            <span>
              <i className="legend-median" /> Median RTT
            </span>
            <span>
              <i className="legend-smoke" /> RTT distribution
            </span>
            <span>
              <i className="legend-loss" /> Packet loss
            </span>
          </div>
        </div>

        <div className="icmp-chart-shell">
          <svg
            aria-label="ICMP latency distribution, median latency and packet loss over time"
            className="icmp-smoke-graph"
            role="img"
            viewBox={`0 0 ${width} ${height}`}
          >
            <defs>
              <filter id="smokeBlur" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="2.2" />
              </filter>
            </defs>

            {yTicks.map((tick) => (
              <g key={tick}>
                <line
                  className="graph-grid"
                  x1={left}
                  x2={width - right}
                  y1={y(tick)}
                  y2={y(tick)}
                />
                <text className="graph-label graph-y-label" x={left - 12} y={y(tick) + 4}>
                  {Math.round(tick)} ms
                </text>
              </g>
            ))}

            {timeTicks.map((tick, index) => {
              const tickX = left + ((tick - startMs) / durationMs) * plotWidth
              const labels = formatTick(tick, durationMs)
              return (
                <g key={tick}>
                  <line
                    className="graph-time-grid"
                    x1={tickX}
                    x2={tickX}
                    y1={top}
                    y2={plotBottom}
                  />
                  {labels.map((label, labelIndex) => (
                    <text
                      className="graph-label graph-time-label"
                      key={label}
                      textAnchor={
                        index === 0
                          ? 'start'
                          : index === timeTicks.length - 1
                            ? 'end'
                            : 'middle'
                      }
                      x={tickX}
                      y={plotBottom + 27 + labelIndex * 15}
                    >
                      {label}
                    </text>
                  ))}
                </g>
              )
            })}

            {points.flatMap((point) => {
              const pointX = x(point.scheduled_at)
              const bins = new Map<number, number>()
              for (const sample of point.rtt_samples_ms) {
                const bucket = Math.round(y(sample) / 3) * 3
                bins.set(bucket, (bins.get(bucket) ?? 0) + 1)
              }
              return [...bins.entries()].map(([bucketY, count]) => {
                const smokeHeight = Math.max(5, count * 2.2)
                return (
                  <rect
                    className="smoke-sample"
                    filter="url(#smokeBlur)"
                    height={smokeHeight}
                    key={`${point.agent_id}-${point.scheduled_at}-${bucketY}`}
                    opacity={Math.min(0.62, 0.09 + count * 0.075)}
                    width={smokeWidth}
                    x={pointX - smokeWidth / 2}
                    y={bucketY - smokeHeight / 2}
                  />
                )
              })
            })}

            {series.flatMap((item, index) =>
              item.segments.map((segment, segmentIndex) => {
                const medianPoints = segment
                  .filter((point) => point.median_rtt_ms !== null)
                  .map((point) => `${x(point.scheduled_at)},${y(point.median_rtt_ms ?? 0)}`)
                  .join(' ')
                if (!medianPoints) return null
                return (
                  <polyline
                    className={`median-line ${seriesClasses[index % seriesClasses.length]}`}
                    key={`${item.agentId}-${segmentIndex}`}
                    points={medianPoints}
                  />
                )
              }),
            )}

            <text className="graph-section-label" x={left} y={lossTop - 9}>
              PACKET LOSS
            </text>
            {points.map((point) => {
              const pointX = x(point.scheduled_at)
              return (
                <rect
                  className={`loss-strip-cell ${lossClass(point.packet_loss_percent)}`}
                  height={lossHeight}
                  key={`loss-${point.agent_id}-${point.scheduled_at}`}
                  width={Math.max(1.5, observationWidth)}
                  x={pointX - observationWidth / 2}
                  y={lossTop}
                />
              )
            })}

            {points.map((point) => {
              const pointX = x(point.scheduled_at)
              const hitWidth = Math.max(8, observationWidth * 2)
              return (
                <rect
                  className="graph-hit-target"
                  height={plotBottom - top}
                  key={`hit-${point.agent_id}-${point.scheduled_at}`}
                  onMouseEnter={() => setHovered(point)}
                  onMouseLeave={() => setHovered(null)}
                  width={hitWidth}
                  x={pointX - hitWidth / 2}
                  y={top}
                />
              )
            })}

            {hovered ? (
              <line
                className="hover-crosshair"
                x1={x(hovered.scheduled_at)}
                x2={x(hovered.scheduled_at)}
                y1={top}
                y2={plotBottom}
              />
            ) : null}
          </svg>

          {hovered ? (
            <div
              className="graph-tooltip"
              style={{
                left: `${Math.min(76, Math.max(8, (x(hovered.scheduled_at) / width) * 100 - 8))}%`,
              }}
            >
              <strong>
                {new Intl.DateTimeFormat(undefined, {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                }).format(new Date(hovered.scheduled_at))}
              </strong>
              <span>{agentNames[hovered.agent_id] ?? hovered.agent_id}</span>
              <dl>
                <div><dt>Median RTT</dt><dd>{formatMs(hovered.median_rtt_ms)}</dd></div>
                <div><dt>Average RTT</dt><dd>{formatMs(hovered.avg_rtt_ms)}</dd></div>
                <div><dt>Minimum RTT</dt><dd>{formatMs(hovered.min_rtt_ms)}</dd></div>
                <div><dt>P95 RTT</dt><dd>{formatMs(hovered.p95_rtt_ms)}</dd></div>
                <div><dt>Maximum RTT</dt><dd>{formatMs(hovered.max_rtt_ms)}</dd></div>
                <div><dt>Jitter</dt><dd>{formatMs(hovered.jitter_ms)}</dd></div>
                <div><dt>Packet loss</dt><dd>{formatPercent(hovered.packet_loss_percent)}</dd></div>
                <div><dt>Packets</dt><dd>{hovered.packets_received} / {hovered.packets_sent}</dd></div>
              </dl>
            </div>
          ) : null}
        </div>

        <div className="loss-legend" aria-label="Packet loss legend">
          <span><i className="loss-none" /> 0%</span>
          <span><i className="loss-trace" /> 0–1%</span>
          <span><i className="loss-low" /> 1–5%</span>
          <span><i className="loss-medium" /> 5–20%</span>
          <span><i className="loss-high" /> &gt;20%</span>
        </div>
      </div>

      <div className="icmp-summary-grid">
        <article className="metric-block">
          <span className="eyebrow">Median RTT</span>
          <strong>{formatMs(latest?.median_rtt_ms ?? null)}</strong>
          <span className="metric-caption">Now</span>
          <div className="metric-triplet">
            <span><b>{formatMs(allSamples.length ? Math.min(...allSamples) : null)}</b><small>Min</small></span>
            <span><b>{formatMs(average(allSamples))}</b><small>Avg</small></span>
            <span><b>{formatMs(allSamples.length ? Math.max(...allSamples) : null)}</b><small>Max</small></span>
          </div>
        </article>
        <article className="metric-block">
          <span className="eyebrow">Packet loss</span>
          <strong>{formatPercent(currentLoss)}</strong>
          <span className="metric-caption">Now</span>
          <div className="metric-triplet">
            <span><b>{formatPercent(minimumLoss)}</b><small>Min</small></span>
            <span><b>{formatPercent(averageLoss)}</b><small>Avg</small></span>
            <span><b>{formatPercent(maximumLoss)}</b><small>Max</small></span>
          </div>
        </article>
        <article className="metric-block">
          <span className="eyebrow">Jitter</span>
          <strong>{formatMs(latest?.jitter_ms ?? null)}</strong>
          <span className="metric-caption">Now</span>
          <div className="metric-triplet">
            <span><b>{formatMs(jitterValues.length ? Math.min(...jitterValues) : null)}</b><small>Min</small></span>
            <span><b>{formatMs(average(jitterValues))}</b><small>Avg</small></span>
            <span><b>{formatMs(jitterValues.length ? Math.max(...jitterValues) : null)}</b><small>Max</small></span>
          </div>
        </article>
        <article className="metric-block">
          <span className="eyebrow">Samples</span>
          <strong>{allSamples.length.toLocaleString()}</strong>
          <span className="metric-caption">Total RTT samples</span>
          <div className="sample-breakdown">
            <b>{latest?.packets_sent ?? 0}</b> per probe · <b>{observations.length}</b> probes
          </div>
        </article>
        <article className="availability-block">
          <div
            className="availability-ring"
            style={{ '--availability': `${availability * 3.6}deg` } as CSSProperties}
          >
            <strong>{availability.toFixed(availability >= 99.95 ? 0 : 1)}%</strong>
          </div>
          <dl>
            <div><dt>Successful</dt><dd>{completed}</dd></div>
            <div><dt>Failed</dt><dd>{failed}</dd></div>
          </dl>
        </article>
      </div>

      <div className="agent-breakdown-card">
        <div className="agent-breakdown-heading">
          <span className="eyebrow">Agent breakdown</span>
          <span className="muted">
            {agentSummaries.length} vantage point{agentSummaries.length === 1 ? '' : 's'}
          </span>
        </div>
        <div className="resource-table-wrap agent-breakdown-wrap">
          <table className="resource-table agent-breakdown-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Status</th>
                <th>Median RTT (now)</th>
                <th>Avg RTT</th>
                <th>P95 RTT</th>
                <th>Packet loss (avg)</th>
                <th>Jitter (now)</th>
                <th>Samples</th>
                <th>Availability</th>
              </tr>
            </thead>
            <tbody>
              {agentSummaries.map((summary) => (
                <tr key={summary.agentId}>
                  <td><strong>{summary.name}</strong></td>
                  <td>
                    <span className={`agent-health agent-health-${summary.assessment}`}>
                      {summary.assessment}
                    </span>
                  </td>
                  <td>
                    <div className="median-with-sparkline">
                      <span>{formatMs(summary.latest?.median_rtt_ms ?? null)}</span>
                      <Sparkline points={summary.sparkline} />
                    </div>
                  </td>
                  <td>{formatMs(summary.averageRtt)}</td>
                  <td>{formatMs(summary.averageP95)}</td>
                  <td>{formatPercent(summary.averageLoss)}</td>
                  <td>{formatMs(summary.latestJitter)}</td>
                  <td>{summary.samples.toLocaleString()}</td>
                  <td>
                    <div className="availability-cell">
                      <span>{formatPercent(summary.availability)}</span>
                      <i><b style={{ width: `${summary.availability}%` }} /></i>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
