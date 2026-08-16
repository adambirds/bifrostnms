import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

const apiUrl =
  process.env.BIFROST_API_INTERNAL_URL ?? 'http://localhost:8000/api/v1'
const authUrl = process.env.NEXT_PUBLIC_AUTH_URL ?? 'http://localhost:3001'

export type CurrentUser = {
  id: string
  email: string
  full_name: string
  is_superuser: boolean
  active_realm_id: string | null
  realms: { id: string; name: string; slug: string; role: string }[]
}

export class ApiRequestError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

export async function requireUser(): Promise<CurrentUser> {
  const cookieStore = await cookies()
  const cookieHeader = cookieStore.toString()
  const response = await fetch(`${apiUrl}/auth/me`, {
    headers: { cookie: cookieHeader },
    cache: 'no-store',
  })
  if (!response.ok) redirect(`${authUrl}/login?next=/`)
  const data = (await response.json()) as { user: CurrentUser }
  return data.user
}

export async function authenticatedApiFetch<T>(path: string): Promise<T> {
  return authenticatedApiRequest<T>(path)
}

export async function authenticatedApiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const cookieStore = await cookies()
  const headers = new Headers(init.headers)
  headers.set('cookie', cookieStore.toString())

  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers,
    cache: 'no-store',
  })
  if (response.status === 401) redirect(`${authUrl}/login?next=/`)
  if (!response.ok) {
    throw new ApiRequestError(response.status, await readApiError(response))
  }
  return (await response.json()) as T
}

async function readApiError(response: Response): Promise<string> {
  const fallback = `BifrostNMS API request failed with status ${response.status}.`
  try {
    const payload = (await response.json()) as unknown
    if (
      typeof payload === 'object' &&
      payload !== null &&
      'detail' in payload &&
      typeof payload.detail === 'string'
    ) {
      return payload.detail
    }
  } catch {
    return fallback
  }
  return fallback
}
