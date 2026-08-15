import AccountShell from '@/components/AccountShell'
import {requireAccountUser} from '@/lib/server-auth'

export default async function AccountPage() {
  const user = await requireAccountUser('/account')
  const activeRealm = user.realms.find(realm => realm.id === user.active_realm_id)

  return (
    <AccountShell user={user} active="account">
      <div className="account-title-row">
        <div>
          <h1>Account</h1>
          <p className="muted">Manage your BifrostNMS identity and account security.</p>
        </div>
      </div>

      <section className="account-panel">
        <h2>Profile</h2>
        <dl className="account-details">
          <div><dt>Name</dt><dd>{user.full_name}</dd></div>
          <div><dt>Email</dt><dd>{user.email}</dd></div>
          <div><dt>Email status</dt><dd>{user.email_verified ? 'Verified' : 'Not verified'}</dd></div>
          <div><dt>Active realm</dt><dd>{activeRealm?.name ?? 'None selected'}</dd></div>
          {user.is_superuser && <div><dt>Installation access</dt><dd>Superuser</dd></div>}
        </dl>
      </section>

      <section className="account-panel account-security-summary">
        <div>
          <h2>Security</h2>
          <p className="muted">Configure two-factor authentication, recovery codes and passkeys.</p>
        </div>
        <a className="secondary account-action" href="/security">Manage security</a>
      </section>
    </AccountShell>
  )
}
