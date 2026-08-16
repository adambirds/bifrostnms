from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

from tortoise.transactions import in_transaction

from bifrostnms.models import (
    Agent,
    AgentConfigurationState,
    AgentGroup,
    AgentGroupMembership,
    Monitor,
    MonitorAgentAssignment,
    MonitorAgentGroupAssignment,
    ProbeType,
    Realm,
    Target,
    TargetGroup,
    TargetGroupMembership,
)
from bifrostnms.schemas import serialize_probe_configuration

MAX_GROUP_DEPTH = 64


class MonitoringDomainError(ValueError):
    """Base class for rejected monitoring-domain changes."""


class RealmBoundaryError(MonitoringDomainError):
    """Raised when a relationship would cross a realm boundary."""


class HierarchyError(MonitoringDomainError):
    """Raised when a group hierarchy would become invalid."""


class ResourceStateError(MonitoringDomainError):
    """Raised when an archived or disabled resource cannot be used."""


class RealmOwnedResource(Protocol):
    realm_id: UUID


class ArchivableResource(RealmOwnedResource, Protocol):
    archived_at: datetime | None


def _require_same_realm(realm: Realm, *resources: RealmOwnedResource) -> None:
    if any(resource.realm_id != realm.id for resource in resources):
        raise RealmBoundaryError("All related resources must belong to the active realm")


def _require_active(*resources: ArchivableResource) -> None:
    if any(resource.archived_at is not None for resource in resources):
        raise ResourceStateError("Archived resources cannot be changed or assigned")


def _validate_schedule(interval_seconds: int, timeout_seconds: int) -> None:
    if interval_seconds < 1:
        raise MonitoringDomainError("Monitor interval must be at least one second")
    if timeout_seconds < 1 or timeout_seconds >= interval_seconds:
        raise MonitoringDomainError(
            "Monitor timeout must be positive and shorter than its interval"
        )


async def _bump_configuration_revisions(agent_ids: Iterable[UUID], realm_id: UUID) -> None:
    for agent_id in set(agent_ids):
        state, _ = await AgentConfigurationState.get_or_create(
            agent_id=agent_id,
            defaults={"realm_id": realm_id},
        )
        state.desired_revision += 1
        state.desired_content_hash = ""
        await state.save(update_fields=["desired_revision", "desired_content_hash", "updated_at"])


async def create_monitor(
    *,
    realm: Realm,
    target: Target,
    name: str,
    probe_type: ProbeType,
    interval_seconds: int,
    timeout_seconds: int,
    configuration: object,
    description: str | None = None,
) -> Monitor:
    _require_same_realm(realm, target)
    _require_active(target)
    if not target.enabled:
        raise ResourceStateError("Disabled targets cannot receive new monitors")
    _validate_schedule(interval_seconds, timeout_seconds)
    normalized = serialize_probe_configuration(probe_type, configuration)
    return await Monitor.create(
        realm=realm,
        target=target,
        name=name,
        description=description,
        probe_type=probe_type,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        configuration=normalized,
    )


async def update_monitor_behavior(
    monitor: Monitor,
    *,
    realm: Realm,
    target: Target,
    probe_type: ProbeType,
    interval_seconds: int,
    timeout_seconds: int,
    configuration: object,
) -> Monitor:
    _require_same_realm(realm, monitor, target)
    _require_active(monitor, target)
    if not target.enabled:
        raise ResourceStateError("Disabled targets cannot receive monitors")
    _validate_schedule(interval_seconds, timeout_seconds)
    normalized = serialize_probe_configuration(probe_type, configuration)
    old_target_id = monitor.target_id
    changed = (
        old_target_id != target.id
        or monitor.probe_type != probe_type
        or monitor.interval_seconds != interval_seconds
        or monitor.timeout_seconds != timeout_seconds
        or monitor.configuration != normalized
    )
    if not changed:
        return monitor

    monitor.target_id = target.id
    monitor.probe_type = probe_type
    monitor.interval_seconds = interval_seconds
    monitor.timeout_seconds = timeout_seconds
    monitor.configuration = normalized
    monitor.revision += 1
    await monitor.save(
        update_fields=[
            "target_id",
            "probe_type",
            "interval_seconds",
            "timeout_seconds",
            "configuration",
            "revision",
            "updated_at",
        ]
    )
    await _bump_configuration_revisions(await effective_agent_ids(monitor), realm.id)
    return monitor


async def _assert_agent_group_parent(group: AgentGroup, parent: AgentGroup | None) -> None:
    if parent is None:
        return
    if parent.realm_id != group.realm_id:
        raise RealmBoundaryError("A group parent must belong to the same realm")
    _require_active(group, parent)
    if parent.id == group.id:
        raise HierarchyError("A group cannot be its own parent")

    current: AgentGroup | None = parent
    for _ in range(MAX_GROUP_DEPTH):
        if current is None or current.parent_id is None:
            return
        if current.parent_id == group.id:
            raise HierarchyError("A group cannot be moved below one of its descendants")
        current = await AgentGroup.filter(id=current.parent_id, realm_id=group.realm_id).first()
    raise HierarchyError(f"Agent group hierarchy exceeds {MAX_GROUP_DEPTH} levels")


async def move_agent_group(group: AgentGroup, parent: AgentGroup | None) -> AgentGroup:
    await _assert_agent_group_parent(group, parent)
    group.parent_id = parent.id if parent is not None else None
    await group.save(update_fields=["parent_id", "updated_at"])
    return group


async def _assert_target_group_parent(group: TargetGroup, parent: TargetGroup | None) -> None:
    if parent is None:
        return
    if parent.realm_id != group.realm_id:
        raise RealmBoundaryError("A group parent must belong to the same realm")
    _require_active(group, parent)
    if parent.id == group.id:
        raise HierarchyError("A group cannot be its own parent")

    current: TargetGroup | None = parent
    for _ in range(MAX_GROUP_DEPTH):
        if current is None or current.parent_id is None:
            return
        if current.parent_id == group.id:
            raise HierarchyError("A group cannot be moved below one of its descendants")
        current = await TargetGroup.filter(id=current.parent_id, realm_id=group.realm_id).first()
    raise HierarchyError(f"Target group hierarchy exceeds {MAX_GROUP_DEPTH} levels")


async def move_target_group(group: TargetGroup, parent: TargetGroup | None) -> TargetGroup:
    await _assert_target_group_parent(group, parent)
    group.parent_id = parent.id if parent is not None else None
    await group.save(update_fields=["parent_id", "updated_at"])
    return group


async def add_agent_to_group(
    *, realm: Realm, group: AgentGroup, agent: Agent
) -> AgentGroupMembership:
    _require_same_realm(realm, group, agent)
    _require_active(group, agent)
    membership, created = await AgentGroupMembership.get_or_create(
        realm=realm, agent_group=group, agent=agent
    )
    if created:
        monitor_ids = await MonitorAgentGroupAssignment.filter(
            realm=realm, agent_group=group, enabled=True
        ).values_list("monitor_id", flat=True)
        if monitor_ids:
            await _bump_configuration_revisions([agent.id], realm.id)
    return membership


async def add_target_to_group(
    *, realm: Realm, group: TargetGroup, target: Target
) -> TargetGroupMembership:
    _require_same_realm(realm, group, target)
    _require_active(group, target)
    membership, _ = await TargetGroupMembership.get_or_create(
        realm=realm, target_group=group, target=target
    )
    return membership


async def assign_monitor_to_agent(
    *, realm: Realm, monitor: Monitor, agent: Agent
) -> MonitorAgentAssignment:
    _require_same_realm(realm, monitor, agent)
    _require_active(monitor, agent)
    if not monitor.enabled or not agent.enabled:
        raise ResourceStateError("Disabled resources cannot receive new assignments")
    assignment, created = await MonitorAgentAssignment.get_or_create(
        realm=realm,
        monitor=monitor,
        agent=agent,
        defaults={"enabled": True},
    )
    if created or not assignment.enabled:
        assignment.enabled = True
        if not created:
            await assignment.save(update_fields=["enabled", "updated_at"])
        await _bump_configuration_revisions([agent.id], realm.id)
    return assignment


async def assign_monitor_to_agent_group(
    *, realm: Realm, monitor: Monitor, group: AgentGroup
) -> MonitorAgentGroupAssignment:
    _require_same_realm(realm, monitor, group)
    _require_active(monitor, group)
    if not monitor.enabled or not group.enabled:
        raise ResourceStateError("Disabled resources cannot receive new assignments")
    assignment, created = await MonitorAgentGroupAssignment.get_or_create(
        realm=realm,
        monitor=monitor,
        agent_group=group,
        defaults={"enabled": True},
    )
    if created or not assignment.enabled:
        assignment.enabled = True
        if not created:
            await assignment.save(update_fields=["enabled", "updated_at"])
        agent_ids = cast(
            list[UUID],
            await AgentGroupMembership.filter(
                realm=realm,
                agent_group=group,
                agent__enabled=True,
                agent__archived_at=None,
            ).values_list("agent_id", flat=True),
        )
        await _bump_configuration_revisions(agent_ids, realm.id)
    return assignment


async def effective_agent_ids(monitor: Monitor) -> set[UUID]:
    if monitor.archived_at is not None or not monitor.enabled:
        return set()
    direct_ids = cast(
        list[UUID],
        await MonitorAgentAssignment.filter(
            realm_id=monitor.realm_id,
            monitor=monitor,
            enabled=True,
            agent__enabled=True,
            agent__archived_at=None,
        ).values_list("agent_id", flat=True),
    )
    group_ids = cast(
        list[UUID],
        await MonitorAgentGroupAssignment.filter(
            realm_id=monitor.realm_id,
            monitor=monitor,
            enabled=True,
            agent_group__enabled=True,
            agent_group__archived_at=None,
        ).values_list("agent_group_id", flat=True),
    )
    group_agent_ids = cast(
        list[UUID],
        await AgentGroupMembership.filter(
            realm_id=monitor.realm_id,
            agent_group_id__in=group_ids,
            agent__enabled=True,
            agent__archived_at=None,
        ).values_list("agent_id", flat=True),
    )
    return set(direct_ids) | set(group_agent_ids)


async def archive_target(*, realm: Realm, target: Target) -> None:
    _require_same_realm(realm, target)
    if target.archived_at is not None:
        return
    archived_at = datetime.now(UTC)
    async with in_transaction():
        target.enabled = False
        target.archived_at = archived_at
        await target.save(update_fields=["enabled", "archived_at", "updated_at"])
        monitors = await Monitor.filter(realm=realm, target=target, archived_at=None).all()
        affected_agent_ids: set[UUID] = set()
        for monitor in monitors:
            affected_agent_ids.update(await effective_agent_ids(monitor))
        await Monitor.filter(realm=realm, target=target, archived_at=None).update(
            enabled=False, archived_at=archived_at
        )
        await _bump_configuration_revisions(affected_agent_ids, realm.id)
