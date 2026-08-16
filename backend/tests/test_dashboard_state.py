from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from bifrostnms.api.dashboard import _history_range
from bifrostnms.config import Settings
from bifrostnms.models import ProbeType
from bifrostnms.monitoring.dashboard import _availability_state, _headline
from bifrostnms.schemas.dashboard import MonitorAgentState


def settings() -> Settings:
    return Settings(
        agent_heartbeat_interval_seconds=30,
        agent_offline_after_seconds=90,
        agent_configuration_poll_interval_seconds=30,
    )


def state(name: str) -> MonitorAgentState:
    return MonitorAgentState(
        monitor_id=uuid4(),
        monitor_name="Web",
        agent_id=uuid4(),
        agent_name="London",
        probe_type=ProbeType.HTTP,
        availability_state=name,  # type: ignore[arg-type]
        desired_config_revision=2,
        acknowledged_config_revision=2,
    )


def row(now: datetime, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "desired_revision": 2,
        "acknowledged_revision": 2,
        "acknowledged_at": now - timedelta(minutes=5),
        "last_heartbeat_at": now - timedelta(seconds=15),
        "interval_seconds": 60,
        "timeout_seconds": 10,
        "last_scheduled_at": now - timedelta(seconds=30),
        "execution_status": "completed",
        "assessment": "healthy",
    }
    values.update(overrides)
    return values


def test_pending_configuration_precedes_connectivity() -> None:
    now = datetime.now(UTC)
    values = row(
        now,
        desired_revision=3,
        acknowledged_revision=2,
        last_heartbeat_at=now - timedelta(minutes=10),
    )
    assert _availability_state(values, now=now, settings=settings()) == "pending_configuration"


def test_agent_stale_and_offline_are_distinct() -> None:
    now = datetime.now(UTC)
    assert (
        _availability_state(
            row(now, last_heartbeat_at=now - timedelta(seconds=75)),
            now=now,
            settings=settings(),
        )
        == "agent_stale"
    )
    assert (
        _availability_state(
            row(now, last_heartbeat_at=now - timedelta(seconds=120)),
            now=now,
            settings=settings(),
        )
        == "agent_offline"
    )


def test_probe_failure_and_target_failure_are_distinct() -> None:
    now = datetime.now(UTC)
    assert (
        _availability_state(
            row(now, execution_status="failed", assessment="unknown"),
            now=now,
            settings=settings(),
        )
        == "probe_error"
    )
    assert (
        _availability_state(
            row(now, execution_status="completed", assessment="unhealthy"),
            now=now,
            settings=settings(),
        )
        == "unhealthy"
    )


def test_overdue_does_not_treat_missing_data_as_success() -> None:
    now = datetime.now(UTC)
    values = row(now, last_scheduled_at=now - timedelta(minutes=5))
    assert _availability_state(values, now=now, settings=settings()) == "overdue"


def test_monitor_headline_requires_distributed_agreement() -> None:
    assert _headline([]) == "disabled"
    assert _headline([state("healthy"), state("healthy")]) == "healthy"
    assert _headline([state("unhealthy"), state("unhealthy")]) == "unhealthy"
    assert _headline([state("healthy"), state("unhealthy")]) == "degraded"
    assert _headline([state("agent_offline")]) == "unknown"


def test_history_range_rejects_more_than_thirty_days() -> None:
    end = datetime.now(UTC)
    with pytest.raises(HTTPException) as exc:
        _history_range(start=end - timedelta(days=31), end=end)
    assert exc.value.status_code == 422
