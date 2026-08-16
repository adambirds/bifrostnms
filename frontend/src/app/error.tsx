'use client'

import { useEffect } from 'react'

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="page-state page-state-error" role="alert">
      <span className="eyebrow">Monitoring data unavailable</span>
      <h1>The dashboard could not load this view.</h1>
      <p>
        No monitoring state has been assumed. Retry the request, or check the
        control-plane service if the problem continues.
      </p>
      <button type="button" onClick={() => reset()}>
        Retry
      </button>
    </div>
  )
}
