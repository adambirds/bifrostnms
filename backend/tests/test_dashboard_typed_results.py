from __future__ import annotations

import json

from bifrostnms.models import ProbeType
from bifrostnms.monitoring.dashboard import _typed_result
from bifrostnms.schemas.dashboard import IcmpProbeResult


def _icmp_payload() -> dict[str, object]:
    return {
        "packets_sent": 20,
        "packets_received": 20,
        "packet_loss_percent": 0.0,
        "min_rtt_ms": 11.2,
        "avg_rtt_ms": 12.4,
        "median_rtt_ms": 12.1,
        "max_rtt_ms": 15.8,
        "p95_rtt_ms": 14.9,
        "jitter_ms": 0.8,
        "rtt_samples_ms": [11.2, 12.1, 15.8],
    }


def test_typed_result_accepts_decoded_json_mapping() -> None:
    result = _typed_result(ProbeType.ICMP, {"result": _icmp_payload()})

    assert isinstance(result, IcmpProbeResult)
    assert result.packets_sent == 20
    assert result.median_rtt_ms == 12.1


def test_typed_result_decodes_json_text_returned_by_database_driver() -> None:
    result = _typed_result(ProbeType.ICMP, {"result": json.dumps(_icmp_payload())})

    assert isinstance(result, IcmpProbeResult)
    assert result.packets_received == 20
    assert result.packet_loss_percent == 0.0
