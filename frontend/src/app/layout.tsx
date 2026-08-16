import type {Metadata} from 'next'
import Link from 'next/link'

import {requireUser} from '@/lib/auth'

import './globals.css'

export const metadata: Metadata = {
  title: 'BifrostNMS',
  description: 'Distributed network monitoring',
}

const authUrl = process.env.NEXT_PUBLIC_AUTH_URL ?? 'http://localhost:3001'

export default async function RootLayout({
  children,
}: Readonly<{children: React.ReactNode}>) {
  const user = await requireUser()
  const realm =
    user.realms.find(item => item.id === user.active_realm_id) ?? user.realms[0]

  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="sidebar">
            <Link className="brand" href="/">
              BifrostNMS
            </Link>
            <div className="realm-switcher">
              <span className="eyebrow">Active realm</span>
              <strong>{realm?.name ?? 'No realm selected'}</strong>
            </div>
            <nav className="primary-nav" aria-label="Primary navigation">
              <Link href="/">Overview</Link>
              <Link href="/targets">Targets</Link>
              <Link href="/agents">Agents</Link>
              <Link href="/monitors">Monitors</Link>
              <Link href="/groups">Groups</Link>
            </nav>
          </aside>
          <div className="workspace">
            <header className="topbar">
              <div>
                <span className="user-name">{user.full_name}</span>
                {user.is_superuser ? (
                  <span className="role-badge">Superuser</span>
                ) : null}
              </div>
              <div className="account-links">
                <a href={`${authUrl}/account`}>Account</a>
                <a href={`${authUrl}/logout`}>Sign out</a>
              </div>
            </header>
            <main className="content">{children}</main>
          </div>
        </div>
      </body>
    </html>
  )
}
