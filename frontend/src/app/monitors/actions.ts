'use server'

import { revalidatePath } from 'next/cache'

import { ApiRequestError, authenticatedApiRequest } from '@/lib/auth'
import { buildMonitorConfiguration, requiredNumber } from '@/lib/monitor-form'
import type { Monitor, ProbeType } from '@/lib/monitoring'

export type MonitorFormState = {
  error: string | null
  success: string | null
}

export const initialMonitorFormState: MonitorFormState = {
  error: null,
  success: null,
}

export async function createMonitorAction(
  previousState: MonitorFormState,
  formData: FormData,
): Promise<MonitorFormState> {
  void previousState

  const name = String(formData.get('name') ?? '').trim()
  const targetId = String(formData.get('target_id') ?? '').trim()
  const description = String(formData.get('description') ?? '').trim()
  const rawProbeType = String(formData.get('probe_type') ?? '')
  const probeTypes: ProbeType[] = ['icmp', 'http', 'tcp', 'dns', 'tls']

  if (!name || !targetId || !probeTypes.includes(rawProbeType as ProbeType)) {
    return { error: 'Name, target and probe type are required.', success: null }
  }

  const probeType = rawProbeType as ProbeType

  try {
    await authenticatedApiRequest<Monitor>('/monitoring/monitors', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        target_id: targetId,
        name,
        description: description || null,
        probe_type: probeType,
        interval_seconds: requiredNumber(formData, 'interval_seconds'),
        timeout_seconds: requiredNumber(formData, 'timeout_seconds'),
        configuration: buildMonitorConfiguration(probeType, formData),
      }),
    })
  } catch (error) {
    return {
      error:
        error instanceof ApiRequestError
          ? error.message
          : 'The monitor could not be created.',
      success: null,
    }
  }

  revalidatePath('/')
  revalidatePath('/monitors')
  return { error: null, success: 'Monitor created.' }
}
