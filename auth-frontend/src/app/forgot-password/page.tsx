'use client'

import Link from 'next/link'
import {FormEvent, useState} from 'react'
import AuthCard from '@/components/AuthCard'
import {authRequest} from '@/lib/api'

export default function ForgotPasswordPage() {
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const email = new FormData(event.currentTarget).get('email')
    setError(null)
    setLoading(true)
    try {
      const result = await authRequest<{detail: string}>('/auth/password/forgot', {
        method: 'POST',
        body: JSON.stringify({email}),
      })
      setMessage(result.detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to request a password reset')
    } finally {
      setLoading(false)
    }
  }

  return <AuthCard>
    <h1>Reset your password</h1>
    <p className="muted">Enter your account email and we will send a reset link if it exists.</p>
    {error && <div className="error">{error}</div>}
    {message && <div className="success">{message}</div>}
    {!message && <form onSubmit={submit}>
      <div className="field"><label htmlFor="email">Email</label><input id="email" name="email" type="email" autoComplete="email" required /></div>
      <button className="primary" disabled={loading}>{loading ? 'Sending…' : 'Send reset link'}</button>
    </form>}
    <p className="footer"><Link href="/login">Return to sign in</Link></p>
  </AuthCard>
}
