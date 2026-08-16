import {
  buildIcmpSeries,
  graphTimeBounds,
  type IcmpVisualizationPoint,
} from '@/lib/icmp-visualization'

type IcmpGraphProps = {
  points: IcmpVisualizationPoint[]
  intervalSeconds: number
  agentNames?: Record<string, string>
}

const width = 900
const height = 300
const padding = 34
const seriesClasses = [
  'series-0',
  'series-1',
  'series-2',
  'series-3',
  'series-4',
  'series-5',
]

export function IcmpGraph({
  points,
  intervalSeconds,
  agentNames = {},
}: IcmpGraphProps) {
  if (points.length === 0) {
    return (
      <div className="empty-graph">
        No ICMP observations in this time range. Missing measurements are shown as
        gaps rather than zero latency.
      </div>
    )
  }

  const samples = points.flatMap((point) => point.rtt_samples_ms)
  const maximum = Math.max(1, ...samples)
  const bounds = graphTimeBounds(points)
  if (!bounds) return null

  const plotWidth = width - padding * 2
  const plotHeight = height - padding * 2
  const x = (scheduledAt: string) =>
    padding +
    ((new Date(scheduledAt).getTime() - bounds.startMs) /
      (bounds.endMs - bounds.startMs)) *
      plotWidth
  const y = (value: number) => padding + plotHeight - (value / maximum) * plotHeight
  const series = buildIcmpSeries(points, intervalSeconds)
  const seriesIndex = new Map(series.map((item, index) => [item.agentId, index]))
  const barWidth = Math.max(2, plotWidth / Math.max(points.length, 80))

  return (
    <div className="graph-wrap">
      <svg
        aria-label="ICMP latency distribution, packet loss and per-agent median latency over time"
        className="icmp-graph"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <g key={fraction}>
            <line
              className="graph-grid"
              x1={padding}
              x2={width - padding}
              y1={padding + plotHeight * fraction}
              y2={padding + plotHeight * fraction}
            />
            <text
              className="graph-label"
              x={2}
              y={padding + plotHeight * fraction + 4}
            >
              {Math.round(maximum * (1 - fraction))}
            </text>
          </g>
        ))}

        {points.map((point) => {
          const pointX = x(point.scheduled_at)
          const index = seriesIndex.get(point.agent_id) ?? 0
          const seriesClass = seriesClasses[index % seriesClasses.length]
          return (
            <g key={`${point.agent_id}-${point.scheduled_at}`}>
              {point.packet_loss_percent > 0 ? (
                <rect
                  className="loss-column"
                  height={plotHeight}
                  opacity={Math.max(0.08, point.packet_loss_percent / 100)}
                  width={barWidth}
                  x={pointX - barWidth / 2}
                  y={padding}
                />
              ) : null}
              {point.rtt_samples_ms.map((sample, sampleIndex) => (
                <circle
                  className={`rtt-sample ${seriesClass}`}
                  cx={pointX}
                  cy={y(sample)}
                  key={`${point.agent_id}-${point.scheduled_at}-${sampleIndex}`}
                  r="1.8"
                />
              ))}
              {point.min_rtt_ms !== null && point.max_rtt_ms !== null ? (
                <line
                  className={`rtt-range ${seriesClass}`}
                  x1={pointX}
                  x2={pointX}
                  y1={y(point.min_rtt_ms)}
                  y2={y(point.max_rtt_ms)}
                />
              ) : null}
            </g>
          )
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
      </svg>
      <div className="graph-legend" aria-label="Graph legend">
        {series.map((item, index) => (
          <span key={item.agentId}>
            <i
              className={`agent-series-key ${seriesClasses[index % seriesClasses.length]}`}
            />
            {agentNames[item.agentId] ?? item.agentId}
          </span>
        ))}
        <span>
          <i className="loss-key" /> Packet loss
        </span>
      </div>
      <p className="graph-note">
        Dots are individual successful RTT samples. Lines show each agent&apos;s median.
        Breaks in a line represent missing observations; they are never interpolated as
        zero.
      </p>
    </div>
  )
}

export type { IcmpVisualizationPoint as IcmpPoint }
