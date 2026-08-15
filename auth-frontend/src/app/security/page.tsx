import AccountShell from '@/components/AccountShell'
import SecuritySettings from '@/components/SecuritySettings'
import {requireAccountUser} from '@/lib/server-auth'

export default async function SecurityPage() {
  const user = await requireAccountUser('/security')

  return (
    <AccountShell user={user} active="security">
      <SecuritySettings />
    </AccountShell>
  )
}
