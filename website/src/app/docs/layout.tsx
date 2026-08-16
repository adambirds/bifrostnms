import Link from 'next/link'

import { userGuides } from '@/lib/docs'

export default function DocsLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="container docs-shell">
      <aside className="docs-sidebar">
        <Link className="docs-home" href="/docs">
          Documentation
        </Link>
        <nav aria-label="Documentation navigation">
          {userGuides.map((guide) => (
            <Link href={`/docs/${guide.slug}`} key={guide.slug}>
              {guide.title}
            </Link>
          ))}
        </nav>
      </aside>
      <article className="docs-content">{children}</article>
    </div>
  )
}
