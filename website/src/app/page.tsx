import Link from 'next/link'

const features = [
  {
    title: 'Observe from everywhere',
    description:
      'Run lightweight Go agents at the network vantage points that matter and compare one target across locations.',
  },
  {
    title: 'Keep the smoke',
    description:
      'Preserve individual ICMP RTT samples, packet loss, jitter and outliers instead of flattening monitoring into one average.',
  },
  {
    title: 'Autonomous agents',
    description:
      'Agents schedule probes locally, retain the last valid configuration and queue observations in SQLite while disconnected.',
  },
  {
    title: 'Native probes',
    description:
      'ICMP, HTTP/HTTPS, TCP, DNS and TLS run natively in Go without making fping, curl or dig normal runtime dependencies.',
  },
  {
    title: 'Self-host first',
    description:
      'A cohesive FastAPI control plane, PostgreSQL/TimescaleDB and Redis deployment keeps the open-source edition understandable.',
  },
  {
    title: 'Cloud-ready architecture',
    description:
      'Realms are a first-class tenant boundary today, allowing the same architecture to power the future hosted service.',
  },
]

export default function HomePage() {
  return (
    <>
      <section className="hero">
        <div className="container hero-grid">
          <div>
            <span className="kicker">Open-source distributed network monitoring</span>
            <h1>See your network from everywhere.</h1>
            <p className="hero-copy">
              BifrostNMS brings the distributed visibility that made SmokePing useful to a
              modern control plane, autonomous Go agents and an operator-focused web
              interface.
            </p>
            <div className="hero-actions">
              <Link className="button primary" href="/docs/getting-started">
                Get started
              </Link>
              <a
                className="button secondary"
                href="https://github.com/adambirds/bifrostnms"
              >
                View on GitHub
              </a>
            </div>
            <p className="hero-note">
              Early development · self-hosted first · BifrostNMS Cloud planned
            </p>
          </div>
          <div className="hero-console" aria-label="Example distributed monitoring state">
            <div className="console-header">
              <span />
              <span />
              <span />
              <strong>example.com / ICMP</strong>
            </div>
            <div className="console-body">
              <div className="console-row">
                <span>London</span>
                <strong className="good">Healthy</strong>
                <code>12.4 ms</code>
              </div>
              <div className="console-row">
                <span>Manchester</span>
                <strong className="good">Healthy</strong>
                <code>18.1 ms</code>
              </div>
              <div className="console-row">
                <span>Frankfurt</span>
                <strong className="warning">Degraded</strong>
                <code>4% loss</code>
              </div>
              <div className="smoke-preview" aria-hidden="true">
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section" id="features">
        <div className="container">
          <div className="section-heading">
            <span className="kicker">Built around the monitoring data</span>
            <h2>Modern tooling without losing the useful bits.</h2>
            <p>
              BifrostNMS treats network location, missing data and latency distribution as
              first-class information rather than hiding them behind a single uptime badge.
            </p>
          </div>
          <div className="feature-grid">
            {features.map((feature) => (
              <article className="feature-card" key={feature.title}>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container split-section">
          <div>
            <span className="kicker">Designed for operators</span>
            <h2>Know whether the target failed, the probe failed, or the vantage point disappeared.</h2>
          </div>
          <div className="state-list">
            <div><strong>Target unhealthy</strong><span>A real observation completed and failed its assessment.</span></div>
            <div><strong>Probe error</strong><span>The execution could not produce a normal target assessment.</span></div>
            <div><strong>Agent offline</strong><span>The monitoring location itself is unavailable.</span></div>
            <div><strong>Missing data</strong><span>An expected observation never arrived; it is not treated as zero.</span></div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container callout">
          <div>
            <span className="kicker">Start self-hosted</span>
            <h2>Follow the complete setup and testing guide.</h2>
            <p>
              The documentation covers realms, agent enrolment, targets, groups, monitors,
              native probes and how to interpret distributed results.
            </p>
          </div>
          <Link className="button primary" href="/docs">
            Read the documentation
          </Link>
        </div>
      </section>
    </>
  )
}
