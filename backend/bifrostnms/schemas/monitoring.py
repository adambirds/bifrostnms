from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from bifrostnms.models import ProbeType


class ProbeConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1


class IcmpProbeConfiguration(ProbeConfiguration):
    packet_count: Annotated[int, Field(ge=1, le=100)] = 20
    packet_interval_ms: Annotated[int, Field(ge=10, le=1000)] = 50
    per_packet_timeout_ms: Annotated[int, Field(ge=1, le=60_000)] | None = None
    payload_size_bytes: Annotated[int, Field(ge=0, le=1400)] = 56
    address_family: Literal["auto", "ipv4", "ipv6"] = "auto"
    maximum_packet_loss_percent: Annotated[float, Field(ge=0, le=100)] | None = None
    maximum_average_rtt_ms: Annotated[float, Field(ge=0)] | None = None


class HttpProbeConfiguration(ProbeConfiguration):
    scheme: Literal["http", "https"] = "https"
    method: Literal["GET", "HEAD"] = "GET"
    path: Annotated[str, Field(min_length=1, max_length=2048)] = "/"
    port: Annotated[int, Field(ge=1, le=65535)] | None = None
    follow_redirects: bool = True
    verify_tls: bool = True
    expected_status_codes: Annotated[list[int], Field(min_length=1, max_length=32)] = Field(
        default_factory=lambda: [200]
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("path must start with '/'")
        return value

    @field_validator("expected_status_codes")
    @classmethod
    def validate_status_codes(cls, value: list[int]) -> list[int]:
        if any(code < 100 or code > 599 for code in value):
            raise ValueError("expected status codes must be between 100 and 599")
        if len(value) != len(set(value)):
            raise ValueError("expected status codes must be unique")
        return value


class TcpProbeConfiguration(ProbeConfiguration):
    port: Annotated[int, Field(ge=1, le=65535)]
    address_family: Literal["auto", "ipv4", "ipv6"] = "auto"


class DnsProbeConfiguration(ProbeConfiguration):
    query_name: Annotated[str, Field(min_length=1, max_length=253)]
    query_type: Literal["A", "AAAA", "CNAME", "MX", "NS", "PTR", "SOA", "TXT"] = "A"
    transport: Literal["udp", "tcp"] = "udp"
    port: Annotated[int, Field(ge=1, le=65535)] = 53
    recursion_desired: bool = True

    @field_validator("query_name")
    @classmethod
    def normalize_query_name(cls, value: str) -> str:
        return value.rstrip(".").lower()


class TlsProbeConfiguration(ProbeConfiguration):
    port: Annotated[int, Field(ge=1, le=65535)] = 443
    server_name: Annotated[str, Field(min_length=1, max_length=253)] | None = None
    verify_certificate: bool = True


type TypedProbeConfiguration = (
    IcmpProbeConfiguration
    | HttpProbeConfiguration
    | TcpProbeConfiguration
    | DnsProbeConfiguration
    | TlsProbeConfiguration
)

_PROBE_CONFIGURATION_ADAPTERS: dict[ProbeType, TypeAdapter[TypedProbeConfiguration]] = {
    ProbeType.ICMP: TypeAdapter(IcmpProbeConfiguration),
    ProbeType.HTTP: TypeAdapter(HttpProbeConfiguration),
    ProbeType.TCP: TypeAdapter(TcpProbeConfiguration),
    ProbeType.DNS: TypeAdapter(DnsProbeConfiguration),
    ProbeType.TLS: TypeAdapter(TlsProbeConfiguration),
}


def validate_probe_configuration(
    probe_type: ProbeType, configuration: object
) -> TypedProbeConfiguration:
    """Validate untrusted JSON against the schema for one probe family."""
    return _PROBE_CONFIGURATION_ADAPTERS[probe_type].validate_python(configuration)


def serialize_probe_configuration(
    probe_type: ProbeType, configuration: object, *, timeout_seconds: int | None = None
) -> dict[str, object]:
    """Return a normalized JSON-ready probe configuration."""
    validated = validate_probe_configuration(probe_type, configuration)
    if isinstance(validated, IcmpProbeConfiguration) and timeout_seconds is not None:
        available_ms = (
            timeout_seconds * 1000 - (validated.packet_count - 1) * validated.packet_interval_ms
        )
        packet_timeout_ms = validated.per_packet_timeout_ms or available_ms
        if available_ms < 1 or packet_timeout_ms > available_ms:
            raise ValueError("ICMP packet sequence does not fit within monitor timeout")
        validated = validated.model_copy(update={"per_packet_timeout_ms": packet_timeout_ms})
    return validated.model_dump(mode="json")
