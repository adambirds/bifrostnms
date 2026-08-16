import pytest
from pydantic import ValidationError

from bifrostnms.models import ProbeType
from bifrostnms.schemas import (
    DnsProbeConfiguration,
    HttpProbeConfiguration,
    IcmpProbeConfiguration,
    TcpProbeConfiguration,
    TlsProbeConfiguration,
    serialize_probe_configuration,
    validate_probe_configuration,
)


@pytest.mark.parametrize(
    ("probe_type", "configuration", "expected_type"),
    [
        (ProbeType.ICMP, {}, IcmpProbeConfiguration),
        (ProbeType.HTTP, {"scheme": "https", "path": "/health"}, HttpProbeConfiguration),
        (ProbeType.TCP, {"port": 443}, TcpProbeConfiguration),
        (ProbeType.DNS, {"query_name": "Example.COM."}, DnsProbeConfiguration),
        (ProbeType.TLS, {"server_name": "example.com"}, TlsProbeConfiguration),
    ],
)
def test_validate_probe_configuration_selects_strict_schema(
    probe_type: ProbeType,
    configuration: dict[str, object],
    expected_type: type[object],
) -> None:
    assert isinstance(validate_probe_configuration(probe_type, configuration), expected_type)


def test_probe_configuration_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_probe_configuration(ProbeType.ICMP, {"command": "ping example.com"})


@pytest.mark.parametrize(
    ("probe_type", "configuration"),
    [
        (ProbeType.HTTP, {"path": "health"}),
        (ProbeType.HTTP, {"expected_status_codes": [200, 200]}),
        (ProbeType.HTTP, {"expected_status_codes": [99]}),
        (ProbeType.TCP, {"port": 0}),
        (ProbeType.DNS, {"query_name": ""}),
        (ProbeType.TLS, {"port": 65536}),
    ],
)
def test_probe_configuration_rejects_invalid_values(
    probe_type: ProbeType, configuration: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        validate_probe_configuration(probe_type, configuration)


def test_probe_configuration_rejects_future_schema_version() -> None:
    with pytest.raises(ValidationError):
        validate_probe_configuration(ProbeType.ICMP, {"schema_version": 2})


def test_probe_configuration_serialization_is_normalized() -> None:
    assert serialize_probe_configuration(ProbeType.DNS, {"query_name": "Example.COM."}) == {
        "schema_version": 1,
        "query_name": "example.com",
        "query_type": "A",
        "transport": "udp",
        "port": 53,
        "recursion_desired": True,
    }


def test_icmp_configuration_materializes_schedule_safe_defaults() -> None:
    assert serialize_probe_configuration(ProbeType.ICMP, {}, timeout_seconds=2) == {
        "schema_version": 1,
        "packet_count": 20,
        "packet_interval_ms": 50,
        "per_packet_timeout_ms": 1050,
        "payload_size_bytes": 56,
        "address_family": "auto",
        "maximum_packet_loss_percent": None,
        "maximum_average_rtt_ms": None,
    }

    with pytest.raises(ValueError, match="does not fit"):
        serialize_probe_configuration(ProbeType.ICMP, {}, timeout_seconds=0)
