'use client'

import {useState} from 'react'
import {authRequest} from '@/lib/api'

export default function EmailVerificationAction() {
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function resend() {
    setLoading(true)
    try {
      const result = await authRequest<{detail: string}>('/auth/email-verification/request', {method: 'POST'})
      setMessage(result.detail)
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Unable to request verification')
    } finally {
      setLoading(false)
    }
  }

  return <div className="inline-action">
    <button className="secondary small" type="button" disabled={loading} onClick={resend}>{loading ? 'Sending…' : 'Resend verification'}</button>
    {message && <span className="muted">{message}</span>}
  </div>
}
