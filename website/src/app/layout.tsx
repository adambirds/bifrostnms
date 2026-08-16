import type { Metadata } from 'next'
import Link from 'next/link'

import './globals.css'

export const metadata: Metadata = {
  title: {
    default: 'BifrostNMS — Distributed network monitoring',
    template: '%s | BifrostNMS',
  },
  description:
    'Open-source distributed network monitoring with lightweight autonomous agents and SmokePing-style latency visibility.',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="container header-inner">
            <Link className="site-brand" href="/">
              <span className="brand-mark">B</span>
              <span>BifrostNMS</span>
            </Link>
            <nav className="site-nav" aria-label="Primary navigation">
              <Link href="/#features">Features</Link>
              <Link href="/docs">Documentation</Link>
              <Link href="/cloud">Cloud</Link>
              <a href="https://github.com/adambirds/bifrostnms">GitHub</a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
        <footer className="site-footer">
          <div className="container footer-inner">
            <div>
              <strong>BifrostNMS</strong>
              <p>See your network from everywhere.</p>
            </div>
            <div className="footer-links">
              <Link href="/docs">Documentation</Link>
              <a href="https://github.com/adambirds/bifrostnms">Source code</a>
              <a href="https://github.com/sponsors/adambirds">Sponsor</a>
            </div>
          </div>
        </footer>
      </body>
    </html>
  )
}
