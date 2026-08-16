'use client'

import {useActionState, useEffect, useRef} from 'react'

import {createAgentAction, type AgentFormState} from '@/app/agents/actions'

const initialState: AgentFormState = {error: null}

export function AgentForm() {
  const [state, action, pending] = useActionState(createAgentAction, initialState)
  const formRef = useRef<HTMLFormElement>(null)

  useEffect(() => {
    if (!pending && state.error === null) formRef.current?.reset()
  }, [pending, state.error])

  return (
    <form ref={formRef} action={action} className="resource-form">
      <label>
        <span>Name</span>
        <input name="name" required maxLength={200} />
      </label>
      <label>
        <span>Description</span>
        <textarea name="description" rows={3} />
      </label>
      {state.error ? <p className="form-error">{state.error}</p> : null}
      <button type="submit" disabled={pending}>
        {pending ? 'Creating…' : 'Create agent'}
      </button>
    </form>
  )
}
