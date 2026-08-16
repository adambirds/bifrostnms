export type IcmpVisualizationPoint = {
  scheduled_at: string
  agent_id: string
  packet_loss_percent: number
  min_rtt_ms: number | null
  median_rtt_ms: number | null
  max_rtt_ms: number | null
  rtt_samples_ms: number[]
}

export type IcmpSeries = {
  agentId: string
  segments: IcmpVisualizationPoint[][]
}

export function buildIcmpSeries(
  points: IcmpVisualizationPoint[],
  intervalSeconds: number,
): IcmpSeries[] {
  const grouped = new Map<string, IcmpVisualizationPoint[]>()
  for (const point of points) {
    const existing = grouped.get(point.agent_id) ?? []
    existing.push(point)
    grouped.set(point.agent_id, existing)
  }

  const maximumGapMs = Math.max(intervalSeconds * 1.75 * 1000, 1)
  return [...grouped.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([agentId, agentPoints]) => {
      const sorted = [...agentPoints].sort(
        (left, right) =>
          new Date(left.scheduled_at).getTime() -
          new Date(right.scheduled_at).getTime(),
      )
      const segments: IcmpVisualizationPoint[][] = []
      for (const point of sorted) {
        const segment = segments.at(-1)
        const previous = segment?.at(-1)
        if (
          !segment ||
          !previous ||
          new Date(point.scheduled_at).getTime() -
            new Date(previous.scheduled_at).getTime() >
            maximumGapMs
        ) {
          segments.push([point])
        } else {
          segment.push(point)
        }
      }
      return { agentId, segments }
    })
}

export function graphTimeBounds(points: IcmpVisualizationPoint[]): {
  startMs: number
  endMs: number
} | null {
  if (!points.length) return null
  const times = points.map((point) => new Date(point.scheduled_at).getTime())
  const startMs = Math.min(...times)
  const endMs = Math.max(...times)
  return {
    startMs,
    endMs: endMs === startMs ? startMs + 1 : endMs,
  }
}
