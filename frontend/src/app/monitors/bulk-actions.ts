'use server'

import { revalidatePath } from 'next/cache'

import { ApiRequestError, authenticatedApiRequest } from '@/lib/auth'
import { buildMonitorConfiguration, requiredNumber } from '@/lib/monitor-form'
import type { BulkMonitorCreateResponse, ProbeType } from '@/lib/monitoring'

export type BulkMonitorFormState = {
  error: string | null
  success: string | null
}

export async function createBulkMonitorsAction(
  previousState: BulkMonitorFormState,
  formData: FormData,
): Promise<BulkMonitorFormState> {
  void previousState

  const mode = String(formData.get('definition_mode') ?? 'new')
  const targetMode = String(formData.get('target_mode') ?? 'group')
  const nameTemplate = String(formData.get('name_template') ?? '').trim()
  const sourceMonitorId = String(formData.get('source_monitor_id') ?? '').trim()
  const targetGroupId = String(formData.get('target_group_id') ?? '').trim()
  const targetIds = formData
    .getAll('target_ids')
    .map((value) => String(value))
    .filter(Boolean)
  const agentIds = formData
    .getAll('agent_ids')
    .map((value) => String(value))
    .filter(Boolean)
  const agentGroupIds = formData
    .getAll('agent_group_ids')
    .map((value) => String(value))
    .filter(Boolean)

  if (!nameTemplate) {
    return { error: 'A monitor name template is required.', success: null }
  }
  if (targetMode === 'group' && !targetGroupId) {
    return { error: 'Select a target group.', success: null }
  }
  if (targetMode === 'selected' && targetIds.length === 0) {
    return { error: 'Select at least one target.', success: null }
  }
  if (mode === 'copy' && !sourceMonitorId) {
    return { error: 'Select the monitor to duplicate.', success: null }
  }

  const payload: Record<string, unknown> = {
    target_ids: targetMode === 'selected' ? targetIds : [],
    target_group_id: targetMode === 'group' ? targetGroupId : null,
    source_monitor_id: mode === 'copy' ? sourceMonitorId : null,
    name_template: nameTemplate,
    agent_ids: agentIds,
    agent_group_ids: agentGroupIds,
    skip_existing: formData.get('skip_existing') === 'on',
  }

  if (mode === 'new') {
    const rawProbeType = String(formData.get('probe_type') ?? '')
    const probeTypes: ProbeType[] = ['icmp', 'http', 'tcp', 'dns', 'tls']
    if (!probeTypes.includes(rawProbeType as ProbeType)) {
      return { error: 'Select a valid probe type.', success: null }
    }
    const probeType = rawProbeType as ProbeType
    const description = String(formData.get('description') ?? '').trim()
    payload.description = description || null
    payload.probe_type = probeType
    payload.interval_seconds = requiredNumber(formData, 'interval_seconds')
    payload.timeout_seconds = requiredNumber(formData, 'timeout_seconds')
    payload.configuration = buildMonitorConfiguration(probeType, formData)
  }

  let result: BulkMonitorCreateResponse
  try {
    result = await authenticatedApiRequest<BulkMonitorCreateResponse>(
      '/monitoring/monitors/bulk',
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
  } catch (error) {
    return {
      error:
        error instanceof ApiRequestError
          ? error.message
          : 'The monitors could not be created.',
      success: null,
    }
  }

  revalidatePath('/')
  revalidatePath('/monitors')
  revalidatePath('/targets')

  const skipped = result.skipped.length
    ? ` ${result.skipped.length} target${result.skipped.length === 1 ? '' : 's'} skipped.`
    : ''
  return {
    error: null,
    success: `${result.created.length} monitor${result.created.length === 1 ? '' : 's'} created.${skipped}`,
  }
}
