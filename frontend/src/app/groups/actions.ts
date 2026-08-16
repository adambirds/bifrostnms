'use server'

import { revalidatePath } from 'next/cache'

import { ApiRequestError, authenticatedApiRequest } from '@/lib/auth'
import type {
  AgentGroup,
  AgentGroupMembership,
  TargetGroup,
  TargetGroupMembership,
} from '@/lib/monitoring'

export type GroupActionState = {
  error: string | null
  success: string | null
}

function actionError(error: unknown, fallback: string): GroupActionState {
  return {
    error: error instanceof ApiRequestError ? error.message : fallback,
    success: null,
  }
}

export async function createAgentGroupAction(
  previousState: GroupActionState,
  formData: FormData,
): Promise<GroupActionState> {
  void previousState

  const name = String(formData.get('name') ?? '').trim()
  const description = String(formData.get('description') ?? '').trim()
  const parentId = String(formData.get('parent_id') ?? '').trim()

  if (!name) return { error: 'Name is required.', success: null }

  try {
    await authenticatedApiRequest<AgentGroup>('/monitoring/agent-groups', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        name,
        description: description || null,
        parent_id: parentId || null,
        enabled: true,
      }),
    })
  } catch (error) {
    return actionError(error, 'The agent group could not be created.')
  }

  revalidatePath('/groups')
  return { error: null, success: 'Agent group created.' }
}

export async function createTargetGroupAction(
  previousState: GroupActionState,
  formData: FormData,
): Promise<GroupActionState> {
  void previousState

  const name = String(formData.get('name') ?? '').trim()
  const description = String(formData.get('description') ?? '').trim()
  const parentId = String(formData.get('parent_id') ?? '').trim()

  if (!name) return { error: 'Name is required.', success: null }

  try {
    await authenticatedApiRequest<TargetGroup>('/monitoring/target-groups', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        name,
        description: description || null,
        parent_id: parentId || null,
      }),
    })
  } catch (error) {
    return actionError(error, 'The target group could not be created.')
  }

  revalidatePath('/groups')
  return { error: null, success: 'Target group created.' }
}

export async function addAgentGroupMembershipAction(
  groupId: string,
  previousState: GroupActionState,
  formData: FormData,
): Promise<GroupActionState> {
  void previousState

  const agentId = String(formData.get('agent_id') ?? '').trim()
  if (!agentId) return { error: 'Select an agent.', success: null }

  try {
    await authenticatedApiRequest<AgentGroupMembership>(
      `/monitoring/agent-groups/${groupId}/agents/${agentId}`,
      { method: 'PUT' },
    )
  } catch (error) {
    return actionError(error, 'The agent could not be added to the group.')
  }

  revalidatePath('/groups')
  return { error: null, success: 'Agent added to group.' }
}

export async function addTargetGroupMembershipAction(
  groupId: string,
  previousState: GroupActionState,
  formData: FormData,
): Promise<GroupActionState> {
  void previousState

  const targetId = String(formData.get('target_id') ?? '').trim()
  if (!targetId) return { error: 'Select a target.', success: null }

  try {
    await authenticatedApiRequest<TargetGroupMembership>(
      `/monitoring/target-groups/${groupId}/targets/${targetId}`,
      { method: 'PUT' },
    )
  } catch (error) {
    return actionError(error, 'The target could not be added to the group.')
  }

  revalidatePath('/groups')
  return { error: null, success: 'Target added to group.' }
}

export async function removeAgentGroupMembershipAction(
  groupId: string,
  agentId: string,
  previousState: GroupActionState,
  formData: FormData,
): Promise<GroupActionState> {
  void previousState
  void formData

  try {
    await authenticatedApiRequest<void>(
      `/monitoring/agent-groups/${groupId}/agents/${agentId}`,
      { method: 'DELETE' },
    )
  } catch (error) {
    return actionError(error, 'The agent could not be removed from the group.')
  }

  revalidatePath('/groups')
  return { error: null, success: 'Agent removed from group.' }
}

export async function removeTargetGroupMembershipAction(
  groupId: string,
  targetId: string,
  previousState: GroupActionState,
  formData: FormData,
): Promise<GroupActionState> {
  void previousState
  void formData

  try {
    await authenticatedApiRequest<void>(
      `/monitoring/target-groups/${groupId}/targets/${targetId}`,
      { method: 'DELETE' },
    )
  } catch (error) {
    return actionError(error, 'The target could not be removed from the group.')
  }

  revalidatePath('/groups')
  return { error: null, success: 'Target removed from group.' }
}
