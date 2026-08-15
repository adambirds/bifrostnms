import Link from 'next/link'
import type {ReactNode} from 'react'
import type {AccountUser} from '@/lib/server-auth'

const dashboardUrl = process.env.NEXT_PUBLIC_DASHBOARD_URL ?? 'http://localhost:3000'

export default function AccountShell({
  user,
  active,
  children,
}: {
  user: AccountUser
  active: 'account' | 'security'
  children: ReactNode
}) {
  return (
    <div className="account-shell">
      <header className="account-header">
        <div className="account-header-inner">
          <div className="brand account-brand">
            <div className="brand-mark">B</div>
            <div>
              <strong>BifrostNMS</strong>
              <div className="muted">Account</div>
            </div>
          </div>
          <div className="account-header-actions">
            <span className="muted">{user.email}</span>
            <a href={dashboardUrl}>Back to dashboard</a>
            <Link href="/logout">Sign out</Link>
          </div>
        </div>
      </header>

      <div className="account-body">
        <aside className="account-nav">
          <Link className={active === 'account' ? 'active' : undefined} href="/account">Account</Link>
          <Link className={active === 'security' ? 'active' : undefined} href="/security">Security</Link>
        </aside>
        <main className="account-content">{children}</main>
      </div>
    </div>
  )
}
