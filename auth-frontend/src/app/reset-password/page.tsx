'use client'

import Link from 'next/link'
import {FormEvent, useState} from 'react'
import AuthCard from '@/components/AuthCard'
import {authRequest} from '@/lib/api'

export default function ResetPasswordPage() {
  const [complete, setComplete] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const password = String(form.get('password') ?? '')
    if (password !== form.get('confirm_password')) {
      setError('Passwords do not match')
      return
    }
    setError(null)
    setLoading(true)
    try {
      await authRequest('/auth/password/reset', {
        method: 'POST',
        body: JSON.stringify({
          token: new URLSearchParams(window.location.search).get('token'),
          password,
        }),
      })
      setComplete(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to reset password')
    } finally {
      setLoading(false)
    }
  }

  return <AuthCard>
    <h1>Choose a new password</h1>
    {error && <div className="error">{error}</div>}
    {complete ? <>
      <div className="success">Your password has been reset. Existing sessions have been signed out.</div>
      <p className="footer"><Link href="/login">Sign in</Link></p>
    </> : <form onSubmit={submit}>
      <div className="field"><label htmlFor="password">New password</label><input id="password" name="password" type="password" minLength={12} autoComplete="new-password" required /></div>
      <div className="field"><label htmlFor="confirm_password">Confirm password</label><input id="confirm_password" name="confirm_password" type="password" minLength={12} autoComplete="new-password" required /></div>
      <button className="primary" disabled={loading}>{loading ? 'Resetting…' : 'Reset password'}</button>
    </form>}
  </AuthCard>
}
