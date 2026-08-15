'use client'

import {startAuthentication} from '@simplewebauthn/browser'
import Link from 'next/link'
import {FormEvent, useState} from 'react'
import AuthCard from '@/components/AuthCard'
import {authRequest, dashboardUrl} from '@/lib/api'

type LoginResult = {
  user: unknown | null
  requires_two_factor: boolean
  challenge_token: string | null
}

type WebAuthnOptions = {
  challenge_id: string
  options: Parameters<typeof startAuthentication>[0]['optionsJSON']
}

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [challengeToken, setChallengeToken] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [useRecoveryCode, setUseRecoveryCode] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [passkeyLoading, setPasskeyLoading] = useState(false)

  function redirectToDashboard() {
    const next = new URLSearchParams(window.location.search).get('next')
    window.location.href = next?.startsWith('/') ? `${dashboardUrl}${next}` : dashboardUrl
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const result = await authRequest<LoginResult>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({email, password}),
      })
      if (result.requires_two_factor && result.challenge_token) {
        setChallengeToken(result.challenge_token)
        return
      }
      redirectToDashboard()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in')
    } finally {
      setLoading(false)
    }
  }

  async function verifyTwoFactor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!challengeToken) return
    setError(null)
    setLoading(true)
    try {
      await authRequest('/auth/2fa/challenge/verify', {
        method: 'POST',
        body: JSON.stringify({
          challenge_token: challengeToken,
          code,
          recovery_code: useRecoveryCode,
        }),
      })
      redirectToDashboard()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed')
    } finally {
      setLoading(false)
    }
  }

  async function signInWithPasskey() {
    setError(null)
    setPasskeyLoading(true)
    try {
      const ceremony = await authRequest<WebAuthnOptions>('/auth/webauthn/authenticate/options', {
        method: 'POST',
      })
      const credential = await startAuthentication({optionsJSON: ceremony.options})
      await authRequest('/auth/webauthn/authenticate/verify', {
        method: 'POST',
        body: JSON.stringify({challenge_id: ceremony.challenge_id, credential}),
      })
      redirectToDashboard()
    } catch (err) {
      if (err instanceof Error && err.name === 'NotAllowedError') return
      setError(err instanceof Error ? err.message : 'Passkey authentication failed')
    } finally {
      setPasskeyLoading(false)
    }
  }

  if (challengeToken) {
    return (
      <AuthCard>
        <h1>Two-factor authentication</h1>
        <p className="muted">
          {useRecoveryCode
            ? 'Enter one of your unused recovery codes.'
            : 'Enter the code from your authenticator app.'}
        </p>
        {error && <div className="error">{error}</div>}
        <form onSubmit={verifyTwoFactor}>
          <div className="field">
            <label htmlFor="code">{useRecoveryCode ? 'Recovery code' : 'Authentication code'}</label>
            <input
              id="code"
              autoComplete="one-time-code"
              inputMode={useRecoveryCode ? undefined : 'numeric'}
              required
              value={code}
              onChange={event => setCode(event.target.value)}
            />
          </div>
          <button className="primary" disabled={loading}>
            {loading ? 'Verifying…' : 'Verify'}
          </button>
        </form>
        <p className="footer">
          <button className="link-button" type="button" onClick={() => {setUseRecoveryCode(value => !value); setCode('')}}>
            {useRecoveryCode ? 'Use authenticator app instead' : 'Use a recovery code'}
          </button>
        </p>
      </AuthCard>
    )
  }

  return (
    <AuthCard>
      <h1>Sign in</h1>
      <p className="muted">Access your BifrostNMS realms and monitoring dashboard.</p>
      {error && <div className="error">{error}</div>}

      <button className="primary passkey" type="button" disabled={passkeyLoading || loading} onClick={signInWithPasskey}>
        {passkeyLoading ? 'Waiting for passkey…' : 'Sign in with a passkey'}
      </button>

      <div className="divider"><span>or</span></div>

      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username webauthn" required value={email} onChange={event => setEmail(event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} />
        </div>
        <button className="primary" disabled={loading || passkeyLoading}>{loading ? 'Signing in…' : 'Sign in'}</button>
      </form>
      <p className="footer">No account yet? <Link href="/signup">Create one</Link></p>
    </AuthCard>
  )
}
