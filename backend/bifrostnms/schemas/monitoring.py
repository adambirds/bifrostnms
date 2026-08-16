from __future__ import annotations

import re
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


_HTTP_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_HTTP_FORBIDDEN_HEADERS = {"authorization", "cookie", "proxy-authorization"}


class HttpHeaderAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[str, Field(min_length=1, max_length=128)]
    value: Annotated[str, Field(max_length=1024)]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if _HTTP_HEADER_NAME.fullmatch(value) is None:
            raise ValueError("header assertion name is invalid")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("header assertion value contains control characters")
        return value


class HttpProbeConfiguration(ProbeConfiguration):
    scheme: Literal["http", "https"] = "https"
    port: Annotated[int, Field(ge=1, le=65535)] | None = None
    path: Annotated[str, Field(min_length=1, max_length=2048)] = "/"
    method: Literal["GET", "HEAD"] = "GET"
    follow_redirects: bool = True
    maximum_redirects: Annotated[int, Field(ge=0, le=10)] = 5
    host_header: Annotated[str, Field(min_length=1, max_length=253)] | None = None
    request_headers: dict[
        Annotated[str, Field(min_length=1, max_length=128)],
        Annotated[str, Field(max_length=1024)],
    ] = Field(default_factory=dict, max_length=32)
    expected_status_codes: Annotated[list[int], Field(min_length=1, max_length=200)] = Field(
        default_factory=lambda: list(range(200, 400))
    )
    expected_header_values: Annotated[list[HttpHeaderAssertion], Field(max_length=32)] = Field(
        default_factory=list
    )
    expected_body_contains: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=1024)]], Field(max_length=16)
    ] = Field(default_factory=list)
    maximum_response_bytes: Annotated[int, Field(ge=1, le=4 * 1024 * 1024)] = 1024 * 1024
    address_family: Literal["auto", "ipv4", "ipv6"] = "auto"

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("path must start with '/'")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("path contains control characters")
        return value

    @field_validator("host_header")
    @classmethod
    def validate_host_header(cls, value: str | None) -> str | None:
        if value is None:
            return None
        hostname = value.rstrip(".")
        labels = hostname.split(".")
        if any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or re.fullmatch(r"[A-Za-z0-9-]+", label) is None
            for label in labels
        ):
            raise ValueError("host_header must be a valid hostname")
        return value

    @field_validator("request_headers")
    @classmethod
    def validate_request_headers(cls, value: dict[str, str]) -> dict[str, str]:
        for name, header_value in value.items():
            if _HTTP_HEADER_NAME.fullmatch(name) is None:
                raise ValueError("request header name is invalid")
            if name.lower() in _HTTP_FORBIDDEN_HEADERS:
                raise ValueError(f"request header {name!r} is not permitted")
            if any(ord(character) < 32 or ord(character) == 127 for character in header_value):
                raise ValueError("request header value contains control characters")
        return value

    @field_validator("expected_status_codes")
    @classmethod
    def validate_status_codes(cls, value: list[int]) -> list[int]:
        if any(code < 100 or code > 599 for code in value):
            raise ValueError("expected status codes must be between 100 and 599")
        if len(value) != len(set(value)):
            raise ValueError("expected status codes must be unique")
        return value

    @field_validator("expected_body_contains")
    @classmethod
    def validate_body_assertions(cls, value: list[str]) -> list[str]:
        for expected in value:
            if any(ord(character) < 32 or ord(character) == 127 for character in expected):
                raise ValueError("body assertion contains control characters")
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
    validated = _PROBE_CONFIGURATION_ADAPTERS[probe_type].validate_python(configuration)
    if (
        isinstance(validated, HttpProbeConfiguration)
        and validated.method == "HEAD"
        and validated.expected_body_contains
    ):
        raise ValueError("HTTP HEAD monitors cannot contain body assertions")
    return validated


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
