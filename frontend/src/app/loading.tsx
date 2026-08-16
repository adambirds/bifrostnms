export default function Loading() {
  return (
    <div className="page-state" role="status" aria-live="polite">
      <span className="eyebrow">BifrostNMS</span>
      <h1>Loading monitoring data…</h1>
      <p>
        Fetching the active realm&apos;s monitoring configuration and observations.
      </p>
    </div>
  )
}
