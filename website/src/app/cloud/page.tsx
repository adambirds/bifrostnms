import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'BifrostNMS Cloud',
  description: 'The planned hosted BifrostNMS control plane.',
}

export default function CloudPage() {
  return (
    <section className="section cloud-page">
      <div className="container narrow">
        <span className="kicker">Coming later</span>
        <h1>BifrostNMS Cloud</h1>
        <p className="hero-copy">
          The open-source control plane comes first. The same realm and agent architecture is
          designed to support a hosted control plane and public monitoring locations without
          creating a separate product model.
        </p>
        <div className="cloud-card">
          <h2>Planned direction</h2>
          <ul>
            <li>Managed control plane with the same BifrostNMS dashboard and APIs.</li>
            <li>Customer realms using the tenancy model already present in self-hosted.</li>
            <li>Hosted public probe locations alongside your own private agents.</li>
            <li>Cloud signup, billing and subscription management added after the open-source V1.</li>
          </ul>
        </div>
        <Link className="button primary" href="/docs/getting-started">
          Start self-hosting today
        </Link>
      </div>
    </section>
  )
}
