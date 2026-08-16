from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction

from bifrostnms.agents.credentials import AgentAuthentication
from bifrostnms.agents.protocol import AgentProtocolError
from bifrostnms.models import (
    AgentConfigurationSnapshot,
    AgentConfigurationState,
    AgentGroupMembership,
    AgentOperationalState,
    Monitor,
    MonitorAgentAssignment,
    MonitorAgentGroupAssignment,
)


@dataclass(frozen=True, slots=True)
class ConfigurationResult:
    snapshot: AgentConfigurationSnapshot
    content: dict[str, Any]


async def _assigned_monitor_ids(
    authentication: AgentAuthentication, connection: BaseDBAsyncClient
) -> set[UUID]:
    direct_ids = cast(
        list[UUID],
        await MonitorAgentAssignment.filter(
            realm=authentication.realm,
            agent=authentication.agent,
            enabled=True,
        )
        .using_db(connection)
        .values_list("monitor_id", flat=True),
    )
    group_ids = cast(
        list[UUID],
        await AgentGroupMembership.filter(
            realm=authentication.realm,
            agent=authentication.agent,
            agent_group__enabled=True,
            agent_group__archived_at=None,
        )
        .using_db(connection)
        .values_list("agent_group_id", flat=True),
    )
    grouped_ids = cast(
        list[UUID],
        await MonitorAgentGroupAssignment.filter(
            realm=authentication.realm,
            agent_group_id__in=group_ids,
            enabled=True,
        )
        .using_db(connection)
        .values_list("monitor_id", flat=True),
    )
    return set(direct_ids) | set(grouped_ids)


def _check_capability(monitor: Monitor, capabilities: dict[str, Any]) -> None:
    probe = capabilities.get("probes", {}).get(str(monitor.probe_type))
    schema_version = monitor.configuration.get("schema_version", 1)
    if (
        not isinstance(probe, dict)
        or probe.get("available") is not True
        or schema_version not in probe.get("schema_versions", [])
    ):
        raise AgentProtocolError(
            status_code=409,
            code="incompatible_capability",
            message="An assigned monitor is not supported by this agent.",
            retryable=False,
            details={"monitor_id": str(monitor.id), "probe_type": str(monitor.probe_type)},
        )


async def get_or_create_configuration(
    authentication: AgentAuthentication,
) -> ConfigurationResult:
    async with in_transaction() as connection:
        state, _ = await AgentConfigurationState.get_or_create(
            realm=authentication.realm, agent=authentication.agent, using_db=connection
        )
        state = (
            await AgentConfigurationState.filter(id=state.id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        if state.desired_revision == 0:
            state.desired_revision = 1
        operational = (
            await AgentOperationalState.filter(
                realm=authentication.realm, agent=authentication.agent
            )
            .using_db(connection)
            .first()
        )
        if operational is None:
            raise AgentProtocolError(
                status_code=409,
                code="capabilities_required",
                message="Send a heartbeat before requesting configuration.",
                retryable=True,
            )
        monitor_ids = await _assigned_monitor_ids(authentication, connection)
        monitors = (
            await Monitor.filter(
                id__in=monitor_ids,
                realm=authentication.realm,
                enabled=True,
                archived_at=None,
                target__enabled=True,
                target__archived_at=None,
            )
            .using_db(connection)
            .select_related("target")
            .order_by("id")
        )
        entries: list[dict[str, Any]] = []
        for monitor in monitors:
            _check_capability(monitor, operational.capabilities)
            schema_version = int(monitor.configuration.get("schema_version", 1))
            entries.append(
                {
                    "monitor_id": str(monitor.id),
                    "target_id": str(monitor.target_id),
                    "monitor_revision": monitor.revision,
                    "target_address": monitor.target.address,
                    "probe_type": str(monitor.probe_type),
                    "probe_schema_version": schema_version,
                    "interval_seconds": monitor.interval_seconds,
                    "timeout_seconds": monitor.timeout_seconds,
                    "missed_run_policy": "skip",
                    "configuration": monitor.configuration,
                }
            )
        hash_input = {
            "configuration_schema_version": 1,
            "agent_id": str(authentication.agent.id),
            "realm_id": str(authentication.realm.id),
            "monitors": entries,
        }
        canonical = json.dumps(hash_input, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(canonical.encode()).hexdigest()
        snapshot, _ = await AgentConfigurationSnapshot.get_or_create(
            realm=authentication.realm,
            agent=authentication.agent,
            revision=state.desired_revision,
            defaults={"content_hash": content_hash, "configuration": hash_input},
            using_db=connection,
        )
        if snapshot.content_hash != content_hash:
            raise AgentProtocolError(
                status_code=409,
                code="configuration_revision_conflict",
                message="Desired configuration changed while its snapshot was generated.",
                retryable=True,
            )
        if state.desired_content_hash != content_hash:
            state.desired_content_hash = content_hash
            await state.save(
                update_fields=[
                    "desired_revision",
                    "desired_content_hash",
                    "updated_at",
                ],
                using_db=connection,
            )
    return ConfigurationResult(snapshot=snapshot, content=hash_input)


async def acknowledge_configuration(
    *,
    authentication: AgentAuthentication,
    revision: int,
    content_hash: str,
    activated_at: datetime,
) -> AgentConfigurationState:
    digest = content_hash.removeprefix("sha256:")
    async with in_transaction() as connection:
        snapshot = (
            await AgentConfigurationSnapshot.filter(
                realm=authentication.realm,
                agent=authentication.agent,
                revision=revision,
                content_hash=digest,
            )
            .using_db(connection)
            .first()
        )
        if snapshot is None:
            raise AgentProtocolError(
                status_code=409,
                code="unknown_configuration",
                message="The acknowledged configuration was not issued to this agent.",
                retryable=False,
            )
        state = (
            await AgentConfigurationState.filter(
                realm=authentication.realm, agent=authentication.agent
            )
            .using_db(connection)
            .select_for_update()
            .get()
        )
        if revision >= state.acknowledged_revision:
            state.acknowledged_revision = revision
            state.acknowledged_content_hash = digest
            state.acknowledged_at = activated_at
            await state.save(
                update_fields=[
                    "acknowledged_revision",
                    "acknowledged_content_hash",
                    "acknowledged_at",
                    "updated_at",
                ],
                using_db=connection,
            )
    return state
