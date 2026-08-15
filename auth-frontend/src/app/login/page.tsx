'use client'

import Link from 'next/link'
import {FormEvent, useState} from 'react'
import AuthCard from '@/components/AuthCard'
import {authRequest, dashboardUrl} from '@/lib/api'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await authRequest('/auth/login', {method: 'POST', body: JSON.stringify({email, password})})
      const next = new URLSearchParams(window.location.search).get('next')
      window.location.href = next?.startsWith('/') ? `${dashboardUrl}${next}` : dashboardUrl
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthCard>
      <h1>Sign in</h1>
      <p className="muted">Access your BifrostNMS realms and monitoring dashboard.</p>
      {error && <div className="error">{error}</div>}
      <form onSubmit={submit}>
        <div className="field"><label htmlFor="email">Email</label><input id="email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></div>
        <button className="primary" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</button>
      </form>
      <p className="footer">No account yet? <Link href="/signup">Create one</Link></p>
    </AuthCard>
  )
}
