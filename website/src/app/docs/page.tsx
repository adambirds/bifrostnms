import type { Metadata } from 'next'
import Link from 'next/link'

import { userGuides } from '@/lib/docs'

export const metadata: Metadata = {
  title: 'Documentation',
  description: 'Learn how to install, configure and operate BifrostNMS.',
}

export default function DocsPage() {
  return (
    <>
      <span className="kicker">BifrostNMS documentation</span>
      <h1>Operate BifrostNMS with confidence.</h1>
      <p className="docs-lead">
        These guides describe the user-facing behavior of the current application: from a
        fresh self-hosted install through agent enrolment, monitor configuration and
        distributed result analysis.
      </p>
      <div className="docs-index">
        {userGuides.map((guide) => (
          <Link className="docs-card" href={`/docs/${guide.slug}`} key={guide.slug}>
            <h2>{guide.title}</h2>
            <p>{guide.summary}</p>
            <span>Read guide →</span>
          </Link>
        ))}
      </div>
    </>
  )
}
