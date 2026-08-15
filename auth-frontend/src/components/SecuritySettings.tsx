'use client'

import {startRegistration} from '@simplewebauthn/browser'
import {QRCodeSVG} from 'qrcode.react'
import {FormEvent, useEffect, useState} from 'react'
import {authRequest} from '@/lib/api'

type SecuritySummary = {
  two_factor_enabled: boolean
  recovery_codes_remaining: number
  passkeys: Array<{
    id: string
    name: string
    device_type: string
    backed_up: boolean
    transports: string[]
    created_at: string
    last_used_at: string | null
  }>
}

type TotpSetup = {method_id: string; secret: string; provisioning_uri: string}
type WebAuthnOptions = {
  challenge_id: string
  options: Parameters<typeof startRegistration>[0]['optionsJSON']
}

export default function SecuritySettings() {
  const [summary, setSummary] = useState<SecuritySummary | null>(null)
  const [setup, setSetup] = useState<TotpSetup | null>(null)
  const [totpCode, setTotpCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const [passkeyName, setPasskeyName] = useState('This device')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function refresh() {
    setSummary(await authRequest<SecuritySummary>('/auth/security'))
  }

  useEffect(() => {
    let cancelled = false

    authRequest<SecuritySummary>('/auth/security').then(
      data => {
        if (!cancelled) setSummary(data)
      },
      err => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unable to load security settings')
        }
      },
    )

    return () => {
      cancelled = true
    }
  }, [])

  async function beginTotp() {
    setError(null)
    setMessage(null)
    setRecoveryCodes([])
    setSetup(await authRequest<TotpSetup>('/auth/2fa/totp/setup', {method: 'POST'}))
  }

  async function verifyTotp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!setup) return
    setBusy(true)
    setError(null)
    try {
      const result = await authRequest<{recovery_codes: string[]}>('/auth/2fa/totp/verify', {
        method: 'POST',
        body: JSON.stringify({method_id: setup.method_id, code: totpCode}),
      })
      setRecoveryCodes(result.recovery_codes)
      setSetup(null)
      setTotpCode('')
      setMessage('Two-factor authentication is enabled. Save the recovery codes now; they will not be shown again.')
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to enable two-factor authentication')
    } finally {
      setBusy(false)
    }
  }

  async function disableTotp() {
    if (!window.confirm('Disable two-factor authentication and invalidate all recovery codes?')) return
    setBusy(true)
    setError(null)
    try {
      await authRequest('/auth/2fa/totp', {method: 'DELETE'})
      setMessage('Two-factor authentication disabled.')
      setRecoveryCodes([])
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to disable two-factor authentication')
    } finally {
      setBusy(false)
    }
  }

  async function addPasskey() {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const ceremony = await authRequest<WebAuthnOptions>('/auth/webauthn/register/options', {method: 'POST'})
      const credential = await startRegistration({optionsJSON: ceremony.options})
      await authRequest('/auth/webauthn/register/verify', {
        method: 'POST',
        body: JSON.stringify({challenge_id: ceremony.challenge_id, credential, name: passkeyName}),
      })
      setMessage('Passkey added.')
      await refresh()
    } catch (err) {
      if (err instanceof Error && err.name === 'NotAllowedError') return
      setError(err instanceof Error ? err.message : 'Unable to add passkey')
    } finally {
      setBusy(false)
    }
  }

  async function removePasskey(id: string) {
    if (!window.confirm('Remove this passkey?')) return
    setBusy(true)
    setError(null)
    try {
      await authRequest(`/auth/webauthn/${id}`, {method: 'DELETE'})
      setMessage('Passkey removed.')
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to remove passkey')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="account-title-row">
        <div>
          <h1>Security</h1>
          <p className="muted">Manage how you sign in to BifrostNMS.</p>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {message && <div className="success">{message}</div>}

      <section className="account-panel security-section">
        <h2>Two-factor authentication</h2>
        <p className="muted">Protect password sign-ins with a TOTP authenticator app and one-time recovery codes.</p>
        {summary?.two_factor_enabled ? (
          <>
            <p>Enabled · {summary.recovery_codes_remaining} recovery codes remaining</p>
            <button className="danger" disabled={busy} onClick={disableTotp}>Disable two-factor authentication</button>
          </>
        ) : (
          <button className="secondary" disabled={busy} onClick={beginTotp}>Set up authenticator app</button>
        )}

        {setup && (
          <div className="setup-panel">
            <QRCodeSVG value={setup.provisioning_uri} size={180} bgColor="#ffffff" fgColor="#071225" />
            <p className="muted">Scan this QR code with your authenticator app, or enter this secret manually:</p>
            <code>{setup.secret}</code>
            <form onSubmit={verifyTotp}>
              <div className="field"><label htmlFor="totp">Verification code</label><input id="totp" inputMode="numeric" autoComplete="one-time-code" required value={totpCode} onChange={e => setTotpCode(e.target.value)} /></div>
              <button className="primary" disabled={busy}>Verify and enable</button>
            </form>
          </div>
        )}

        {recoveryCodes.length > 0 && (
          <div className="setup-panel">
            <h3>Recovery codes</h3>
            <p className="muted">Store these somewhere safe. Each code can only be used once.</p>
            <div className="recovery-grid">{recoveryCodes.map(code => <code key={code}>{code}</code>)}</div>
          </div>
        )}
      </section>

      <section className="account-panel security-section">
        <h2>Passkeys</h2>
        <p className="muted">Use Face ID, Touch ID, Windows Hello, a security key, or a synced passkey for passwordless sign-in.</p>
        <div className="passkey-add"><input aria-label="Passkey name" value={passkeyName} onChange={e => setPasskeyName(e.target.value)} /><button className="secondary" disabled={busy} onClick={addPasskey}>Add passkey</button></div>
        <div className="passkey-list">
          {summary?.passkeys.map(passkey => (
            <div className="passkey-row" key={passkey.id}>
              <div><strong>{passkey.name}</strong><div className="muted">{passkey.device_type || 'Authenticator'}{passkey.last_used_at ? ` · last used ${new Date(passkey.last_used_at).toLocaleString()}` : ''}</div></div>
              <button className="danger small" disabled={busy} onClick={() => removePasskey(passkey.id)}>Remove</button>
            </div>
          ))}
          {summary && summary.passkeys.length === 0 && <p className="muted">No passkeys registered yet.</p>}
        </div>
      </section>
    </>
  )
}
