'use client'

import Link from 'next/link'
import {useSearchParams} from 'next/navigation'
import {Suspense, useEffect, useState} from 'react'
import AuthCard from '@/components/AuthCard'
import {authRequest} from '@/lib/api'

function VerifyEmailContent() {
  const token = useSearchParams().get('token')
  const [error, setError] = useState<string | null>(null)
  const [verified, setVerified] = useState(false)

  useEffect(() => {
    if (!token) return
    void authRequest('/auth/email-verification/confirm', {
      method: 'POST',
      body: JSON.stringify({token}),
    }).then(() => setVerified(true)).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : 'Unable to verify email')
    })
  }, [token])

  const visibleError = token ? error : 'The verification link is missing its token.'

  return <AuthCard>
    <h1>Verify your email</h1>
    {!visibleError && !verified && <p className="muted">Verifying your link…</p>}
    {visibleError && <div className="error">{visibleError}</div>}
    {verified && <div className="success">Your email address is verified.</div>}
    <p className="footer"><Link href={verified ? '/account' : '/login'}>{verified ? 'Return to your account' : 'Return to sign in'}</Link></p>
  </AuthCard>
}

export default function VerifyEmailPage() {
  return <Suspense fallback={<AuthCard><p className="muted">Loading verification link…</p></AuthCard>}>
    <VerifyEmailContent />
  </Suspense>
}
