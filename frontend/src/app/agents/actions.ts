'use server'

import { revalidatePath } from 'next/cache'

import { ApiRequestError, authenticatedApiRequest } from '@/lib/auth'
import type { Agent, AgentEnrolmentToken } from '@/lib/monitoring'

export type AgentFormState = { error: string | null }

export type AgentEnrolmentState = {
  error: string | null
  token: AgentEnrolmentToken | null
}

export async function createAgentAction(
  _previousState: AgentFormState,
  formData: FormData,
): Promise<AgentFormState> {
  const name = String(formData.get('name') ?? '').trim()
  const description = String(formData.get('description') ?? '').trim()

  if (!name) return { error: 'Name is required.' }

  try {
    await authenticatedApiRequest<Agent>('/monitoring/agents', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        name,
        description: description || null,
        enabled: true,
      }),
    })
  } catch (error) {
    return {
      error:
        error instanceof ApiRequestError
          ? error.message
          : 'The agent could not be created.',
    }
  }

  revalidatePath('/')
  revalidatePath('/agents')
  return { error: null }
}

export async function issueAgentEnrolmentAction(
  agentId: string,
  previousState: AgentEnrolmentState,
  formData: FormData,
): Promise<AgentEnrolmentState> {
  void previousState
  void formData

  try {
    const token = await authenticatedApiRequest<AgentEnrolmentToken>(
      `/monitoring/agents/${agentId}/enrolment-tokens`,
      { method: 'POST' },
    )
    return { error: null, token }
  } catch (error) {
    return {
      error:
        error instanceof ApiRequestError
          ? error.message
          : 'The enrolment token could not be issued.',
      token: null,
    }
  }
}
