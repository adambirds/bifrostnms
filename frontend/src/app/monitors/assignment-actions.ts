'use server'

import { revalidatePath } from 'next/cache'

import { ApiRequestError, authenticatedApiRequest } from '@/lib/auth'
import type {
  MonitorAgentAssignment,
  MonitorAgentGroupAssignment,
} from '@/lib/monitoring'

export type MonitorAssignmentState = {
  error: string | null
  success: string | null
}

export const initialMonitorAssignmentState: MonitorAssignmentState = {
  error: null,
  success: null,
}

function assignmentError(
  error: unknown,
  fallback = 'The monitor assignment could not be created.',
): MonitorAssignmentState {
  return {
    error: error instanceof ApiRequestError ? error.message : fallback,
    success: null,
  }
}

export async function assignMonitorToAgentAction(
  monitorId: string,
  previousState: MonitorAssignmentState,
  formData: FormData,
): Promise<MonitorAssignmentState> {
  void previousState

  const agentId = String(formData.get('agent_id') ?? '').trim()
  if (!agentId) return { error: 'Select an agent.', success: null }

  try {
    await authenticatedApiRequest<MonitorAgentAssignment>(
      `/monitoring/monitors/${monitorId}/agents/${agentId}`,
      { method: 'PUT' },
    )
  } catch (error) {
    return assignmentError(error)
  }

  revalidatePath('/monitors')
  return { error: null, success: 'Monitor assigned to agent.' }
}

export async function assignMonitorToAgentGroupAction(
  monitorId: string,
  previousState: MonitorAssignmentState,
  formData: FormData,
): Promise<MonitorAssignmentState> {
  void previousState

  const groupId = String(formData.get('agent_group_id') ?? '').trim()
  if (!groupId) return { error: 'Select an agent group.', success: null }

  try {
    await authenticatedApiRequest<MonitorAgentGroupAssignment>(
      `/monitoring/monitors/${monitorId}/agent-groups/${groupId}`,
      { method: 'PUT' },
    )
  } catch (error) {
    return assignmentError(error)
  }

  revalidatePath('/monitors')
  return { error: null, success: 'Monitor assigned to agent group.' }
}

export async function removeMonitorAgentAssignmentAction(
  monitorId: string,
  agentId: string,
  previousState: MonitorAssignmentState,
  formData: FormData,
): Promise<MonitorAssignmentState> {
  void previousState
  void formData

  try {
    await authenticatedApiRequest<void>(
      `/monitoring/monitors/${monitorId}/agents/${agentId}`,
      { method: 'DELETE' },
    )
  } catch (error) {
    return assignmentError(error, 'The agent assignment could not be removed.')
  }

  revalidatePath('/monitors')
  return { error: null, success: 'Agent assignment removed.' }
}

export async function removeMonitorAgentGroupAssignmentAction(
  monitorId: string,
  groupId: string,
  previousState: MonitorAssignmentState,
  formData: FormData,
): Promise<MonitorAssignmentState> {
  void previousState
  void formData

  try {
    await authenticatedApiRequest<void>(
      `/monitoring/monitors/${monitorId}/agent-groups/${groupId}`,
      { method: 'DELETE' },
    )
  } catch (error) {
    return assignmentError(
      error,
      'The agent group assignment could not be removed.',
    )
  }

  revalidatePath('/monitors')
  return { error: null, success: 'Agent group assignment removed.' }
}
