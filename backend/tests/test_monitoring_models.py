from bifrostnms.models import (
    Agent,
    AgentConfigurationSnapshot,
    AgentConfigurationState,
    AgentCredential,
    AgentGroup,
    AgentGroupMembership,
    Monitor,
    MonitorAgentAssignment,
    MonitorAgentGroupAssignment,
    ProbeType,
    Target,
    TargetGroup,
    TargetGroupMembership,
)


def test_v1_probe_types_are_stable() -> None:
    assert {probe.value for probe in ProbeType} == {
        "icmp",
        "http",
        "tcp",
        "dns",
        "tls",
    }


def test_monitoring_resources_have_explicit_realm_ownership() -> None:
    realm_owned_models = (
        Agent,
        AgentConfigurationSnapshot,
        AgentConfigurationState,
        AgentCredential,
        AgentGroup,
        AgentGroupMembership,
        Monitor,
        MonitorAgentAssignment,
        MonitorAgentGroupAssignment,
        Target,
        TargetGroup,
        TargetGroupMembership,
    )

    for model in realm_owned_models:
        assert "realm" in model._meta.fields_map
        assert not model._meta.fields_map["realm"].null


def test_monitor_defaults_begin_at_first_revision() -> None:
    monitor = Monitor(
        name="Public website",
        probe_type=ProbeType.HTTP,
        interval_seconds=60,
        timeout_seconds=10,
    )

    assert monitor.enabled is True
    assert monitor.revision == 1
    assert monitor.configuration == {}


def test_agent_configuration_state_starts_unsynchronised() -> None:
    state = AgentConfigurationState()

    assert state.desired_revision == 0
    assert state.acknowledged_revision == 0
    assert state.desired_content_hash == ""
