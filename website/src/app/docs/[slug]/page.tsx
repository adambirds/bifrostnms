import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { getUserGuide, userGuides } from '@/lib/docs'

type PageProps = {
  params: Promise<{ slug: string }>
}

export function generateStaticParams() {
  return userGuides.map((guide) => ({ slug: guide.slug }))
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const guide = getUserGuide((await params).slug)
  if (!guide) return {}
  return {
    title: guide.title,
    description: guide.summary,
  }
}

export default async function UserGuidePage({ params }: PageProps) {
  const guide = getUserGuide((await params).slug)
  if (!guide) notFound()

  return (
    <>
      <span className="kicker">User guide</span>
      <h1>{guide.title}</h1>
      <p className="docs-lead">{guide.summary}</p>
      <div className="guide-sections">
        {guide.sections.map((section) => (
          <section key={section.heading}>
            <h2>{section.heading}</h2>
            {section.paragraphs?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
            {section.bullets ? (
              <ul>
                {section.bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}
              </ul>
            ) : null}
            {section.code ? <pre><code>{section.code}</code></pre> : null}
            {section.note ? <aside className="docs-note">{section.note}</aside> : null}
          </section>
        ))}
      </div>
    </>
  )
}
