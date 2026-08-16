'use client'

import {useActionState, useEffect, useRef} from 'react'

import {
  createTargetAction,
  type TargetFormState,
} from '@/app/targets/actions'

const initialState: TargetFormState = {error: null}

export function TargetForm() {
  const [state, action, pending] = useActionState(createTargetAction, initialState)
  const formRef = useRef<HTMLFormElement>(null)

  useEffect(() => {
    if (!pending && state.error === null) formRef.current?.reset()
  }, [pending, state.error])

  return (
    <form ref={formRef} action={action} className="resource-form">
      <div className="form-grid">
        <label>
          <span>Name</span>
          <input name="name" required maxLength={200} />
        </label>
        <label>
          <span>Hostname or IP address</span>
          <input name="address" required maxLength={253} />
        </label>
      </div>
      <label>
        <span>Description</span>
        <textarea name="description" rows={3} />
      </label>
      {state.error ? <p className="form-error">{state.error}</p> : null}
      <button type="submit" disabled={pending}>
        {pending ? 'Creating…' : 'Create target'}
      </button>
    </form>
  )
}
