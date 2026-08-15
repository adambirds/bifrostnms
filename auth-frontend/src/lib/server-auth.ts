import {cookies} from 'next/headers'
import {redirect} from 'next/navigation'

const apiUrl = process.env.BIFROST_API_INTERNAL_URL ?? 'http://localhost:8000/api/v1'

export type AccountUser = {
  id: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  email_verified: boolean
  is_superuser: boolean
  active_realm_id: string | null
  realms: {id: string; name: string; slug: string; role: string}[]
}

export async function requireAccountUser(nextPath: string): Promise<AccountUser> {
  const cookieStore = await cookies()
  const response = await fetch(`${apiUrl}/auth/me`, {
    headers: {cookie: cookieStore.toString()},
    cache: 'no-store',
  })

  if (!response.ok) {
    redirect(`/login?next=${encodeURIComponent(nextPath)}`)
  }

  const data = await response.json()
  return data.user as AccountUser
}
