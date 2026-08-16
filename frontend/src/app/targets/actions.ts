'use server'

import { revalidatePath } from 'next/cache'

import { ApiRequestError, authenticatedApiRequest } from '@/lib/auth'
import type { Target } from '@/lib/monitoring'

export type TargetFormState = { error: string | null }

export async function createTargetAction(
  _previousState: TargetFormState,
  formData: FormData,
): Promise<TargetFormState> {
  const name = String(formData.get('name') ?? '').trim()
  const address = String(formData.get('address') ?? '').trim()
  const description = String(formData.get('description') ?? '').trim()

  if (!name || !address) {
    return { error: 'Name and address are required.' }
  }

  try {
    await authenticatedApiRequest<Target>('/monitoring/targets', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        name,
        address,
        description: description || null,
        enabled: true,
      }),
    })
  } catch (error) {
    return {
      error:
        error instanceof ApiRequestError
          ? error.message
          : 'The target could not be created.',
    }
  }

  revalidatePath('/')
  revalidatePath('/targets')
  return { error: null }
}
