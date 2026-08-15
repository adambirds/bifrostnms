import {cookies} from 'next/headers'
import {redirect} from 'next/navigation'

const apiUrl = process.env.BIFROST_API_INTERNAL_URL ?? 'http://localhost:8000/api/v1'
const authUrl = process.env.NEXT_PUBLIC_AUTH_URL ?? 'http://localhost:3001'

export type CurrentUser = {
  id: string
  email: string
  full_name: string
  is_superuser: boolean
  active_realm_id: string | null
  realms: {id: string; name: string; slug: string; role: string}[]
}

export async function requireUser(): Promise<CurrentUser> {
  const cookieStore = await cookies()
  const cookieHeader = cookieStore.toString()
  const response = await fetch(`${apiUrl}/auth/me`, {headers: {cookie: cookieHeader}, cache: 'no-store'})
  if (!response.ok) redirect(`${authUrl}/login?next=/`)
  const data = await response.json()
  return data.user as CurrentUser
}
