from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from tortoise.exceptions import IntegrityError

from bifrostnms.models import (
    Agent,
    AgentGroup,
    Monitor,
    ProbeType,
    Realm,
    Target,
    TargetGroup,
    TargetGroupMembership,
)
from bifrostnms.monitoring.domain import (
    MonitoringDomainError,
    ResourceStateError,
    assign_monitor_to_agent,
    assign_monitor_to_agent_group,
    create_monitor,
)
from bifrostnms.schemas.monitoring_api import BulkMonitorCreate


@dataclass(frozen=True, slots=True)
class SkippedMonitorTarget:
    target_id: UUID
    target_name: str
    reason: str


def _render_monitor_name(
    template: str,
    *,
    target: Target,
    probe_type: ProbeType,
    source_monitor: Monitor | None,
) -> str:
    rendered = (
        template.replace("{target}", target.name)
        .replace("{address}", target.address)
        .replace("{probe}", probe_type.value.upper())
        .replace("{source}", source_monitor.name if source_monitor is not None else "")
        .strip()
    )
    if "{" in rendered or "}" in rendered:
        raise MonitoringDomainError(
            "Monitor name templates only support {target}, {address}, {probe} and {source}"
        )
    if not rendered:
        raise MonitoringDomainError("Monitor name template produced an empty name")
    if len(rendered) > 200:
        raise MonitoringDomainError(
            "Monitor name template produced a name longer than 200 characters"
        )
    return rendered


async def _resolve_targets(*, realm: Realm, payload: BulkMonitorCreate) -> list[Target]:
    target_ids = set(payload.target_ids)
    if payload.target_group_id is not None:
        group = await TargetGroup.filter(
            id=payload.target_group_id,
            realm=realm,
            archived_at=None,
        ).first()
        if group is None:
            raise ResourceStateError("Target group not found")
        group_target_ids = cast(
            list[UUID],
            await TargetGroupMembership.filter(
                realm=realm,
                target_group=group,
            ).values_list("target_id", flat=True),
        )
        target_ids.update(group_target_ids)

    targets = await Target.filter(
        id__in=target_ids,
        realm=realm,
        archived_at=None,
    ).order_by("name")
    resolved_ids = {target.id for target in targets}
    missing_ids = target_ids - resolved_ids
    if missing_ids:
        raise ResourceStateError("One or more selected targets do not exist in the active realm")
    return list(targets)


async def _resolve_assignments(
    *, realm: Realm, payload: BulkMonitorCreate
) -> tuple[list[Agent], list[AgentGroup]]:
    agents = await Agent.filter(
        id__in=payload.agent_ids,
        realm=realm,
        enabled=True,
        archived_at=None,
    ).order_by("name")
    groups = await AgentGroup.filter(
        id__in=payload.agent_group_ids,
        realm=realm,
        enabled=True,
        archived_at=None,
    ).order_by("name")
    if len(agents) != len(payload.agent_ids):
        raise ResourceStateError("One or more selected agents are unavailable")
    if len(groups) != len(payload.agent_group_ids):
        raise ResourceStateError("One or more selected agent groups are unavailable")
    return list(agents), list(groups)


async def create_monitors_bulk(
    *, realm: Realm, payload: BulkMonitorCreate
) -> tuple[list[Monitor], list[SkippedMonitorTarget]]:
    targets = await _resolve_targets(realm=realm, payload=payload)
    agents, agent_groups = await _resolve_assignments(realm=realm, payload=payload)

    source_monitor: Monitor | None = None
    if payload.source_monitor_id is not None:
        source_monitor = await Monitor.filter(
            id=payload.source_monitor_id,
            realm=realm,
            archived_at=None,
        ).first()
        if source_monitor is None:
            raise ResourceStateError("Source monitor not found")

    probe_type = source_monitor.probe_type if source_monitor is not None else payload.probe_type
    interval_seconds = (
        source_monitor.interval_seconds if source_monitor is not None else payload.interval_seconds
    )
    timeout_seconds = (
        source_monitor.timeout_seconds if source_monitor is not None else payload.timeout_seconds
    )
    configuration = (
        source_monitor.configuration if source_monitor is not None else payload.configuration
    )
    description = (
        payload.description
        if payload.description is not None
        else source_monitor.description
        if source_monitor is not None
        else None
    )
    if (
        probe_type is None
        or interval_seconds is None
        or timeout_seconds is None
        or configuration is None
    ):
        raise MonitoringDomainError("Bulk monitor definition is incomplete")

    created: list[Monitor] = []
    skipped: list[SkippedMonitorTarget] = []
    for target in targets:
        if not target.enabled:
            skipped.append(SkippedMonitorTarget(target.id, target.name, "Target is disabled"))
            continue

        name = _render_monitor_name(
            payload.name_template,
            target=target,
            probe_type=probe_type,
            source_monitor=source_monitor,
        )
        if (
            payload.skip_existing
            and await Monitor.filter(
                realm=realm,
                target=target,
                probe_type=probe_type,
                interval_seconds=interval_seconds,
                timeout_seconds=timeout_seconds,
                configuration=configuration,
                archived_at=None,
            ).exists()
        ):
            skipped.append(
                SkippedMonitorTarget(
                    target.id,
                    target.name,
                    "An equivalent monitor already exists on this target",
                )
            )
            continue
        if await Monitor.filter(realm=realm, name=name, archived_at=None).exists():
            skipped.append(
                SkippedMonitorTarget(
                    target.id,
                    target.name,
                    f"A monitor named {name!r} already exists",
                )
            )
            continue

        try:
            monitor = await create_monitor(
                realm=realm,
                target=target,
                name=name,
                description=description,
                probe_type=probe_type,
                interval_seconds=interval_seconds,
                timeout_seconds=timeout_seconds,
                configuration=configuration,
            )
        except IntegrityError:
            skipped.append(
                SkippedMonitorTarget(
                    target.id,
                    target.name,
                    "Monitor creation conflicted with another change",
                )
            )
            continue

        for agent in agents:
            await assign_monitor_to_agent(realm=realm, monitor=monitor, agent=agent)
        for group in agent_groups:
            await assign_monitor_to_agent_group(realm=realm, monitor=monitor, group=group)
        created.append(monitor)

    return created, skipped
