from __future__ import annotations

from uuid import uuid4

from bifrostnms.models import ProbeType
from bifrostnms.monitoring.target_dashboard import _target_headline
from bifrostnms.schemas.dashboard import MonitorHeadline, TargetMonitorSummary


def monitor(headline: MonitorHeadline) -> TargetMonitorSummary:
    return TargetMonitorSummary(
        monitor_id=uuid4(),
        monitor_name="Probe",
        probe_type=ProbeType.ICMP,
        headline=headline,
        enabled=True,
        effective_agents=1,
        healthy_agents=1 if headline == "healthy" else 0,
        unhealthy_agents=1 if headline == "unhealthy" else 0,
        unavailable_agents=0,
        coverage_percent=100,
    )


def test_target_headline_requires_all_monitors_to_be_healthy() -> None:
    assert _target_headline([monitor("healthy"), monitor("healthy")], enabled=True) == "healthy"
    assert _target_headline([monitor("healthy"), monitor("degraded")], enabled=True) == "degraded"
    assert _target_headline([monitor("healthy"), monitor("unhealthy")], enabled=True) == "unhealthy"
    assert _target_headline([monitor("healthy"), monitor("unknown")], enabled=True) == "unknown"


def test_target_headline_handles_disabled_and_unmonitored_targets() -> None:
    assert _target_headline([], enabled=True) == "unknown"
    assert _target_headline([monitor("healthy")], enabled=False) == "disabled"
