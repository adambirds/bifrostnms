from __future__ import annotations

from datetime import UTC, datetime

from bifrostnms.agents.credentials import AgentAuthentication
from bifrostnms.models import AgentConfigurationState, AgentOperationalState
from bifrostnms.schemas.agent_protocol import AgentHeartbeatRequest


async def record_heartbeat(
    *, authentication: AgentAuthentication, payload: AgentHeartbeatRequest
) -> tuple[AgentOperationalState, AgentConfigurationState]:
    received_at = datetime.now(UTC)
    clock_offset_ms = round((received_at - payload.agent_time).total_seconds() * 1000)
    operational_state, _ = await AgentOperationalState.update_or_create(
        realm=authentication.realm,
        agent=authentication.agent,
        defaults={
            "last_heartbeat_at": received_at,
            "agent_version": payload.agent_version,
            "platform": payload.platform,
            "architecture": payload.architecture,
            "hostname": payload.hostname,
            "capabilities": payload.capabilities.model_dump(mode="json"),
            "active_configuration_revision": payload.active_configuration_revision,
            "known_desired_configuration_revision": (payload.known_desired_configuration_revision),
            "queue_depth": payload.queue_depth,
            "queue_bytes": payload.queue_bytes,
            "oldest_pending_observation_at": payload.oldest_pending_observation_at,
            "database_health": payload.database_health.value,
            "scheduler_state": payload.scheduler_state.value,
            "agent_time": payload.agent_time,
            "clock_offset_ms": clock_offset_ms,
            "warnings": payload.warnings,
        },
    )
    configuration_state, _ = await AgentConfigurationState.get_or_create(
        realm=authentication.realm,
        agent=authentication.agent,
    )
    return operational_state, configuration_state
