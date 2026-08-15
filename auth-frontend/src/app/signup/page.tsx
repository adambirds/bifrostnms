'use client'

import Link from 'next/link'
import {FormEvent, useState} from 'react'
import AuthCard from '@/components/AuthCard'
import {authRequest, dashboardUrl} from '@/lib/api'

export default function SignupPage() {
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setError(null)
    setLoading(true)
    try {
      await authRequest('/auth/signup', {
        method: 'POST',
        body: JSON.stringify({
          email: form.get('email'), password: form.get('password'),
          first_name: form.get('first_name'), last_name: form.get('last_name'), realm_name: form.get('realm_name'),
        }),
      })
      window.location.href = dashboardUrl
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create account')
    } finally { setLoading(false) }
  }

  return (
    <AuthCard>
      <h1>Create account</h1>
      <p className="muted">Your first realm is created automatically. You can add more later.</p>
      {error && <div className="error">{error}</div>}
      <form onSubmit={submit}>
        <div className="grid2">
          <div className="field"><label htmlFor="first_name">First name</label><input id="first_name" name="first_name" required /></div>
          <div className="field"><label htmlFor="last_name">Last name</label><input id="last_name" name="last_name" required /></div>
        </div>
        <div className="field"><label htmlFor="email">Email</label><input id="email" name="email" type="email" autoComplete="email" required /></div>
        <div className="field"><label htmlFor="realm_name">Realm name</label><input id="realm_name" name="realm_name" placeholder="Home Lab" /></div>
        <div className="field"><label htmlFor="password">Password</label><input id="password" name="password" type="password" minLength={12} autoComplete="new-password" required /></div>
        <button className="primary" disabled={loading}>{loading ? 'Creating account…' : 'Create account'}</button>
      </form>
      <p className="footer">Already have an account? <Link href="/login">Sign in</Link></p>
    </AuthCard>
  )
}
