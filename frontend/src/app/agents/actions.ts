'use server'

import {revalidatePath} from 'next/cache'

import {ApiRequestError, authenticatedApiRequest} from '@/lib/auth'
import type {Agent} from '@/lib/monitoring'

export type AgentFormState = {error: string | null}

export async function createAgentAction(
  _previousState: AgentFormState,
  formData: FormData,
): Promise<AgentFormState> {
  const name = String(formData.get('name') ?? '').trim()
  const description = String(formData.get('description') ?? '').trim()

  if (!name) return {error: 'Name is required.'}

  try {
    await authenticatedApiRequest<Agent>('/monitoring/agents', {
      method: 'POST',
      headers: {'content-type': 'application/json'},
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
  return {error: null}
}
