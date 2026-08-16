type IcmpPoint = {
  scheduled_at: string
  agent_id: string
  packet_loss_percent: number
  min_rtt_ms: number | null
  median_rtt_ms: number | null
  max_rtt_ms: number | null
  rtt_samples_ms: number[]
}

type IcmpGraphProps = {
  points: IcmpPoint[]
}

const width = 900
const height = 260
const padding = 28

export function IcmpGraph({points}: IcmpGraphProps) {
  if (points.length === 0) {
    return <div className="empty-graph">Waiting for the first ICMP observation.</div>
  }

  const samples = points.flatMap(point => point.rtt_samples_ms)
  const maximum = Math.max(1, ...samples)
  const plotWidth = width - padding * 2
  const plotHeight = height - padding * 2
  const x = (index: number) =>
    padding + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth)
  const y = (value: number) => padding + plotHeight - (value / maximum) * plotHeight
  const agentIDs = [...new Set(points.map(point => point.agent_id))]

  return (
    <div className="graph-wrap">
      <svg
        aria-label="ICMP latency distribution over time"
        className="icmp-graph"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        {[0, 0.25, 0.5, 0.75, 1].map(fraction => (
          <g key={fraction}>
            <line
              className="graph-grid"
              x1={padding}
              x2={width - padding}
              y1={padding + plotHeight * fraction}
              y2={padding + plotHeight * fraction}
            />
            <text className="graph-label" x={2} y={padding + plotHeight * fraction + 4}>
              {Math.round(maximum * (1 - fraction))}
            </text>
          </g>
        ))}
        {points.map((point, index) => {
          const pointX = x(index)
          const barWidth = Math.max(2, plotWidth / Math.max(points.length, 60))
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
                  className="rtt-sample"
                  cx={pointX}
                  cy={y(sample)}
                  key={`${point.agent_id}-${point.scheduled_at}-${sample}-${sampleIndex}`}
                  r="1.8"
                />
              ))}
              {point.min_rtt_ms !== null && point.max_rtt_ms !== null ? (
                <line
                  className="rtt-range"
                  x1={pointX}
                  x2={pointX}
                  y1={y(point.min_rtt_ms)}
                  y2={y(point.max_rtt_ms)}
                />
              ) : null}
            </g>
          )
        })}
        {agentIDs.map(agentID => {
          const medianPath = points
            .map((point, index) =>
              point.agent_id === agentID && point.median_rtt_ms !== null
                ? `${x(index)},${y(point.median_rtt_ms)}`
                : null,
            )
            .filter((value): value is string => value !== null)
            .join(' ')
          return medianPath ? (
            <polyline className="median-line" key={agentID} points={medianPath} />
          ) : null
        })}
      </svg>
      <div className="graph-legend">
        <span><i className="sample-key" />Successful RTT samples</span>
        <span><i className="median-key" />Median latency</span>
        <span><i className="loss-key" />Packet loss</span>
      </div>
    </div>
  )
}

export type {IcmpPoint}
