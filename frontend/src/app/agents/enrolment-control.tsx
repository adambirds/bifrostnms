'use client'

import { useActionState, useState } from 'react'

import {
  initialAgentEnrolmentState,
  issueAgentEnrolmentAction,
} from '@/app/agents/actions'

import styles from './enrolment-control.module.css'

export function EnrolmentControl({ agentId }: { agentId: string }) {
  const action = issueAgentEnrolmentAction.bind(null, agentId)
  const [state, formAction, pending] = useActionState(
    action,
    initialAgentEnrolmentState,
  )
  const [copyStatus, setCopyStatus] = useState<string | null>(null)

  async function copyToken() {
    if (!state.token) return

    try {
      await navigator.clipboard.writeText(state.token.enrolment_token)
      setCopyStatus('Copied')
    } catch {
      setCopyStatus('Copy failed')
    }
  }

  return (
    <div className={styles.control}>
      <form action={formAction}>
        <button type="submit" disabled={pending}>
          {pending
            ? 'Issuing…'
            : state.token
              ? 'Issue replacement token'
              : 'Issue enrolment token'}
        </button>
      </form>
      {state.error ? <p className="form-error">{state.error}</p> : null}
      {state.token ? (
        <div className={styles.tokenPanel} aria-live="polite">
          <p>
            <strong>Enrolment token</strong>
          </p>
          <p className={styles.warning}>
            This secret is shown only in this response. Copy it now. Issuing a
            replacement invalidates the previous unused token.
          </p>
          <div className={styles.tokenRow}>
            <code className={styles.token}>{state.token.enrolment_token}</code>
            <button
              className={styles.secondaryButton}
              type="button"
              onClick={copyToken}
            >
              {copyStatus ?? 'Copy token'}
            </button>
          </div>
          <p className={styles.expiry}>
            Expires {new Date(state.token.expires_at).toLocaleString()}.
          </p>
          <p className="muted">
            On the agent host, paste the token when prompted and replace the
            control-plane URL with the externally reachable BifrostNMS URL.
          </p>
          <pre className={styles.command}>
            <code>{`read -rsp 'Enrolment token: ' BIFROSTNMS_AGENT_ENROLMENT_TOKEN; echo
export BIFROSTNMS_AGENT_ENROLMENT_TOKEN
bifrost-agent enrol --control-plane 'https://bifrost.example.com'
unset BIFROSTNMS_AGENT_ENROLMENT_TOKEN`}</code>
          </pre>
        </div>
      ) : null}
    </div>
  )
}
