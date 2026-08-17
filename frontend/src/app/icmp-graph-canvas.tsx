'use client'

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent,
} from 'react'

import { buildIcmpSeries, type IcmpVisualizationPoint } from '@/lib/icmp-visualization'

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
const maximumRenderedObservations = 1600
const utcFormatter = (options: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat('en-GB', { ...options, timeZone: 'UTC' })

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

function latestByTime<T extends { scheduled_at: string }>(items: T[]): T | null {
  if (!items.length) return null
  return [...items].sort(
    (leftItem, rightItem) =>
      new Date(rightItem.scheduled_at).getTime() - new Date(leftItem.scheduled_at).getTime(),
  )[0]
}

function formatTick(timestamp: number, durationMs: number): string {
  const date = new Date(timestamp)
  if (durationMs <= 24 * 60 * 60 * 1000) {
    return utcFormatter({ hour: '2-digit', minute: '2-digit' }).format(date)
  }
  if (durationMs <= 7 * 24 * 60 * 60 * 1000) {
    return utcFormatter({ weekday: 'short', day: 'numeric', hour: '2-digit' }).format(date)
  }
  return utcFormatter({ day: 'numeric', month: 'short' }).format(date)
}

function packetLossColour(loss: number): string {
  if (loss <= 0) return '#526070'
  if (loss <= 1) return '#38c976'
  if (loss <= 5) return '#f4d03f'
  if (loss <= 20) return '#f39c35'
  return '#ef5350'
}

function medianColour(index: number): string {
  return ['#45d483', '#63b3ff', '#f6c85f', '#e995ff', '#ff9da6', '#a9d18e'][index % 6]
}

function Sparkline({ points }: { points: IcmpPoint[] }) {
  const values = finite(points.map((point) => point.median_rtt_ms))
  if (values.length < 2) return <span className="sparkline-empty">—</span>
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const spread = Math.max(maximum - minimum, 1)
  const polyline = values
    .map((value, index) => {
      const sparkX = (index / Math.max(values.length - 1, 1)) * 110
      const sparkY = 24 - ((value - minimum) / spread) * 20
      return `${sparkX},${sparkY}`
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
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const hoverFrameRef = useRef<number | null>(null)
  const [hovered, setHovered] = useState<IcmpPoint | null>(null)
  const startMs = new Date(rangeStart).getTime()
  const endMs = new Date(rangeEnd).getTime()
  const durationMs = Math.max(endMs - startMs, 1)
  const plotWidth = width - left - right
  const plotHeight = plotBottom - top

  const sortedPoints = useMemo(
    () =>
      [...points].sort(
        (leftPoint, rightPoint) =>
          new Date(leftPoint.scheduled_at).getTime() -
          new Date(rightPoint.scheduled_at).getTime(),
      ),
    [points],
  )
  const allSamples = useMemo(
    () => sortedPoints.flatMap((point) => point.rtt_samples_ms),
    [sortedPoints],
  )
  const p99 = percentile(allSamples, 0.99) ?? 1
  const absoluteMax = Math.max(1, ...allSamples)
  const yMaximum = Math.max(10, Math.ceil(Math.min(absoluteMax, p99 * 1.25) / 5) * 5)
  const x = (scheduledAt: string) =>
    left + ((new Date(scheduledAt).getTime() - startMs) / durationMs) * plotWidth
  const y = (value: number) =>
    top + plotHeight - (Math.min(value, yMaximum) / yMaximum) * plotHeight

  const series = useMemo(
    () => buildIcmpSeries(sortedPoints, intervalSeconds),
    [sortedPoints, intervalSeconds],
  )

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !sortedPoints.length) return
    const context = canvas.getContext('2d')
    if (!context) return

    const devicePixelRatio = window.devicePixelRatio || 1
    canvas.width = Math.round(width * devicePixelRatio)
    canvas.height = Math.round(height * devicePixelRatio)
    context.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0)
    context.clearRect(0, 0, width, height)

    context.fillStyle = '#071225'
    context.fillRect(0, 0, width, height)

    context.font = '12px Inter, ui-sans-serif, system-ui, sans-serif'
    context.textBaseline = 'middle'
    context.strokeStyle = '#203150'
    context.fillStyle = '#7388ab'
    context.lineWidth = 1

    for (let index = 0; index < 5; index += 1) {
      const value = yMaximum * (1 - index / 4)
      const yPosition = top + (plotHeight * index) / 4
      context.beginPath()
      context.moveTo(left, yPosition)
      context.lineTo(width - right, yPosition)
      context.stroke()
      context.textAlign = 'right'
      context.fillText(`${Math.round(value)} ms`, left - 12, yPosition)
    }

    const tickCount = 7
    for (let index = 0; index < tickCount; index += 1) {
      const timestamp = startMs + (durationMs * index) / (tickCount - 1)
      const xPosition = left + (plotWidth * index) / (tickCount - 1)
      context.strokeStyle = '#14233d'
      context.beginPath()
      context.moveTo(xPosition, top)
      context.lineTo(xPosition, plotBottom)
      context.stroke()
      context.fillStyle = '#7388ab'
      context.textAlign = index === 0 ? 'left' : index === tickCount - 1 ? 'right' : 'center'
      context.fillText(formatTick(timestamp, durationMs), xPosition, plotBottom + 28)
    }

    const renderStep = Math.max(1, Math.ceil(sortedPoints.length / maximumRenderedObservations))
    const renderedPoints = sortedPoints.filter((_, index) => index % renderStep === 0)
    const observationWidth = Math.max(
      1.2,
      Math.min(7, (intervalSeconds * 1000 * plotWidth * renderStep) / durationMs),
    )

    context.save()
    context.globalCompositeOperation = 'lighter'
    for (const point of renderedPoints) {
      const pointX = x(point.scheduled_at)
      const bins = new Map<number, number>()
      for (const sample of point.rtt_samples_ms) {
        const bucket = Math.round(y(sample) / 3) * 3
        bins.set(bucket, (bins.get(bucket) ?? 0) + 1)
      }
      for (const [bucketY, count] of bins.entries()) {
        context.fillStyle = `rgba(190, 202, 215, ${Math.min(0.36, 0.045 + count * 0.035)})`
        context.fillRect(
          pointX - Math.max(1.5, observationWidth * 0.9) / 2,
          bucketY - Math.max(2, count * 0.75),
          Math.max(1.5, observationWidth * 0.9),
          Math.max(4, count * 1.5),
        )
      }
    }
    context.restore()

    series.forEach((item, seriesIndex) => {
      context.strokeStyle = medianColour(seriesIndex)
      context.lineWidth = 2
      context.lineJoin = 'round'
      for (const segment of item.segments) {
        let started = false
        context.beginPath()
        for (const point of segment) {
          if (point.median_rtt_ms === null) continue
          const pointX = x(point.scheduled_at)
          const pointY = y(point.median_rtt_ms)
          if (!started) {
            context.moveTo(pointX, pointY)
            started = true
          } else {
            context.lineTo(pointX, pointY)
          }
        }
        if (started) context.stroke()
      }
    })

    context.fillStyle = '#78c9ff'
    context.font = '700 11px Inter, ui-sans-serif, system-ui, sans-serif'
    context.textAlign = 'left'
    context.fillText('PACKET LOSS', left, lossTop - 10)

    for (const point of renderedPoints) {
      const pointX = x(point.scheduled_at)
      context.fillStyle = packetLossColour(point.packet_loss_percent)
      context.fillRect(pointX - observationWidth / 2, lossTop, observationWidth, lossHeight)
    }
  }, [durationMs, endMs, intervalSeconds, plotHeight, plotWidth, series, sortedPoints, startMs, yMaximum])

  useEffect(
    () => () => {
      if (hoverFrameRef.current !== null) cancelAnimationFrame(hoverFrameRef.current)
    },
    [],
  )

  const handleMouseMove = (event: MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas || !sortedPoints.length) return
    const rect = canvas.getBoundingClientRect()
    const relativeX = ((event.clientX - rect.left) / rect.width) * width
    const hoveredTimestamp = startMs + ((relativeX - left) / plotWidth) * durationMs
    if (hoverFrameRef.current !== null) cancelAnimationFrame(hoverFrameRef.current)
    hoverFrameRef.current = requestAnimationFrame(() => {
      let low = 0
      let high = sortedPoints.length - 1
      while (low < high) {
        const middle = Math.floor((low + high) / 2)
        const middleTime = new Date(sortedPoints[middle].scheduled_at).getTime()
        if (middleTime < hoveredTimestamp) low = middle + 1
        else high = middle
      }
      const candidates = [sortedPoints[low], sortedPoints[Math.max(0, low - 1)]].filter(Boolean)
      const nearest = candidates.reduce((best, candidate) =>
        Math.abs(new Date(candidate.scheduled_at).getTime() - hoveredTimestamp) <
        Math.abs(new Date(best.scheduled_at).getTime() - hoveredTimestamp)
          ? candidate
          : best,
      )
      setHovered((current) =>
        current?.scheduled_at === nearest.scheduled_at && current.agent_id === nearest.agent_id
          ? current
          : nearest,
      )
    })
  }

  const latest = latestByTime(sortedPoints)
  const losses = sortedPoints.map((point) => point.packet_loss_percent)
  const currentLoss = latest?.packet_loss_percent ?? 0
  const minimumLoss = losses.length ? Math.min(...losses) : 0
  const averageLoss = average(losses) ?? 0
  const maximumLoss = Math.max(0, ...losses)
  const jitterValues = finite(sortedPoints.map((point) => point.jitter_ms))
  const completed = observations.filter((observation) => observation.execution_status === 'completed').length
  const failed = observations.filter((observation) => observation.execution_status === 'failed').length
  const availability = observations.length ? (completed / observations.length) * 100 : 0

  const agentSummaries: AgentSummary[] = [...new Set(observations.map((item) => item.agent_id))]
    .map((agentId) => {
      const agentPoints = sortedPoints.filter((point) => point.agent_id === agentId)
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
              agentObservations.length) * 100
          : 0,
        assessment: agentLatestObservation?.assessment ?? 'unknown',
        sparkline: agentPoints.slice(-48),
      }
    })
    .sort((leftSummary, rightSummary) => leftSummary.name.localeCompare(rightSummary.name))

  if (!sortedPoints.length) {
    return <div className="empty-graph">No successful ICMP measurements in this time range. Missing measurements are shown as gaps rather than zero latency.</div>
  }

  return (
    <div className="smokeping-dashboard">
      <div className="historical-chart-card">
        <div className="chart-title-row">
          <div>
            <span className="eyebrow">Historical latency</span>
            <strong>
              {utcFormatter({ day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(startMs))} – {utcFormatter({ day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(endMs))} UTC
            </strong>
          </div>
          <div className="modern-graph-legend">
            <span><i className="legend-median" /> Median RTT</span>
            <span><i className="legend-smoke" /> RTT distribution</span>
            <span><i className="legend-loss" /> Packet loss</span>
          </div>
        </div>

        <div className="icmp-chart-shell canvas-chart-shell">
          <canvas
            aria-label="ICMP latency distribution, median latency and packet loss over time"
            className="icmp-smoke-canvas"
            onMouseLeave={() => setHovered(null)}
            onMouseMove={handleMouseMove}
            ref={canvasRef}
          />
          {hovered ? (
            <div className="graph-tooltip canvas-tooltip">
              <strong>{utcFormatter({ day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(hovered.scheduled_at))} UTC</strong>
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
          <span><i className="loss-none" /> 0%</span><span><i className="loss-trace" /> 0–1%</span><span><i className="loss-low" /> 1–5%</span><span><i className="loss-medium" /> 5–20%</span><span><i className="loss-high" /> &gt;20%</span>
        </div>
      </div>

      <div className="icmp-summary-grid">
        <article className="metric-block"><span className="eyebrow">Median RTT</span><strong>{formatMs(latest?.median_rtt_ms ?? null)}</strong><span className="metric-caption">Now</span><div className="metric-triplet"><span><b>{formatMs(allSamples.length ? Math.min(...allSamples) : null)}</b><small>Min</small></span><span><b>{formatMs(average(allSamples))}</b><small>Avg</small></span><span><b>{formatMs(allSamples.length ? Math.max(...allSamples) : null)}</b><small>Max</small></span></div></article>
        <article className="metric-block"><span className="eyebrow">Packet loss</span><strong>{formatPercent(currentLoss)}</strong><span className="metric-caption">Now</span><div className="metric-triplet"><span><b>{formatPercent(minimumLoss)}</b><small>Min</small></span><span><b>{formatPercent(averageLoss)}</b><small>Avg</small></span><span><b>{formatPercent(maximumLoss)}</b><small>Max</small></span></div></article>
        <article className="metric-block"><span className="eyebrow">Jitter</span><strong>{formatMs(latest?.jitter_ms ?? null)}</strong><span className="metric-caption">Now</span><div className="metric-triplet"><span><b>{formatMs(jitterValues.length ? Math.min(...jitterValues) : null)}</b><small>Min</small></span><span><b>{formatMs(average(jitterValues))}</b><small>Avg</small></span><span><b>{formatMs(jitterValues.length ? Math.max(...jitterValues) : null)}</b><small>Max</small></span></div></article>
        <article className="metric-block"><span className="eyebrow">Samples</span><strong>{allSamples.length.toLocaleString('en-GB')}</strong><span className="metric-caption">Total RTT samples</span><div className="sample-breakdown"><b>{latest?.packets_sent ?? 0}</b> per probe · <b>{observations.length}</b> probes</div></article>
        <article className="availability-block"><div className="availability-ring" style={{ '--availability': `${availability * 3.6}deg` } as CSSProperties}><strong>{availability.toFixed(availability >= 99.95 ? 0 : 1)}%</strong></div><dl><div><dt>Successful</dt><dd>{completed}</dd></div><div><dt>Failed</dt><dd>{failed}</dd></div></dl></article>
      </div>

      <div className="agent-breakdown-card">
        <div className="agent-breakdown-heading"><span className="eyebrow">Agent breakdown</span><span className="muted">{agentSummaries.length} vantage point{agentSummaries.length === 1 ? '' : 's'}</span></div>
        <div className="resource-table-wrap agent-breakdown-wrap"><table className="resource-table agent-breakdown-table"><thead><tr><th>Agent</th><th>Status</th><th>Median RTT (now)</th><th>Avg RTT</th><th>P95 RTT</th><th>Packet loss (avg)</th><th>Jitter (now)</th><th>Samples</th><th>Availability</th></tr></thead><tbody>
          {agentSummaries.map((summary) => <tr key={summary.agentId}><td><strong>{summary.name}</strong></td><td><span className={`agent-health agent-health-${summary.assessment}`}>{summary.assessment}</span></td><td><div className="median-with-sparkline"><span>{formatMs(summary.latest?.median_rtt_ms ?? null)}</span><Sparkline points={summary.sparkline} /></div></td><td>{formatMs(summary.averageRtt)}</td><td>{formatMs(summary.averageP95)}</td><td>{formatPercent(summary.averageLoss)}</td><td>{formatMs(summary.latestJitter)}</td><td>{summary.samples.toLocaleString('en-GB')}</td><td><div className="availability-cell"><span>{formatPercent(summary.availability)}</span><i><b style={{ width: `${summary.availability}%` }} /></i></div></td></tr>)}
        </tbody></table></div>
      </div>
    </div>
  )
}
