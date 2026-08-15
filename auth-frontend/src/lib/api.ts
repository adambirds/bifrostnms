export const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'
export const dashboardUrl = process.env.NEXT_PUBLIC_DASHBOARD_URL ?? 'http://localhost:3000'

export type Realm = {id: string; name: string; slug: string; role: string}
export type User = {
  id: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  email_verified: boolean
  active_realm_id: string | null
  realms: Realm[]
}

export async function authRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    credentials: 'include',
    headers: {'Content-Type': 'application/json', ...(init?.headers ?? {})},
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({detail: 'Request failed'}))
    throw new Error(body.detail ?? 'Request failed')
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
