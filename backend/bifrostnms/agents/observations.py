from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction

from bifrostnms.agents.credentials import AgentAuthentication
from bifrostnms.models import AgentConfigurationSnapshot
from bifrostnms.schemas.agent_protocol import (
    AgentObservation,
    AgentObservationResult,
    AgentObservationUpload,
)

MAXIMUM_OBSERVATION_AGE = timedelta(days=30)
MAXIMUM_FUTURE_SKEW = timedelta(minutes=5)


def _rejected(
    observation: AgentObservation, code: str, *, retryable: bool = False
) -> AgentObservationResult:
    return AgentObservationResult(
        scheduled_at=observation.scheduled_at,
        observation_id=observation.observation_id,
        disposition="rejected",
        code=code,
        retryable=retryable,
    )


def _canonical_hash(observation: AgentObservation) -> str:
    content = json.dumps(
        observation.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(content).hexdigest()


async def _insert_common(
    connection: BaseDBAsyncClient,
    authentication: AgentAuthentication,
    upload: AgentObservationUpload,
    observation: AgentObservation,
    content_hash: str,
) -> bool:
    rows = await connection.execute_query_dict(
        """
        INSERT INTO observations (
            scheduled_at, observation_id, realm_id, agent_id, monitor_id,
            probe_type, monitor_revision, agent_config_revision, started_at,
            finished_at, execution_status, assessment, error_category,
            error_code, error_message, agent_clock_offset_ms,
            canonical_payload_hash
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
            $13, $14, $15, $16, $17
        ) ON CONFLICT (scheduled_at, observation_id) DO NOTHING
        RETURNING observation_id
        """,
        [
            observation.scheduled_at,
            observation.observation_id,
            authentication.realm.id,
            authentication.agent.id,
            observation.monitor_id,
            observation.probe_type,
            observation.monitor_revision,
            upload.agent_config_revision,
            observation.started_at,
            observation.finished_at,
            observation.execution_status,
            observation.assessment,
            observation.error_category,
            observation.error_code,
            observation.error_message,
            observation.agent_clock_offset_ms,
            content_hash,
        ],
    )
    return bool(rows)


async def _existing_hash(
    connection: BaseDBAsyncClient, observation: AgentObservation
) -> str | None:
    _, rows = await connection.execute_query(
        """
        SELECT canonical_payload_hash FROM observations
        WHERE scheduled_at = $1 AND observation_id = $2
        """,
        [observation.scheduled_at, observation.observation_id],
    )
    return rows[0]["canonical_payload_hash"] if rows else None


async def _insert_typed_result(
    connection: BaseDBAsyncClient,
    authentication: AgentAuthentication,
    observation: AgentObservation,
) -> None:
    if observation.result is None:
        return
    identity: list[Any] = [
        observation.scheduled_at,
        observation.observation_id,
        authentication.realm.id,
        authentication.agent.id,
        observation.monitor_id,
    ]
    data = observation.result.model_dump()
    specifications = {
        "icmp": (
            "icmp_results",
            [
                "packets_sent",
                "packets_received",
                "packet_loss_percent",
                "min_rtt_ms",
                "avg_rtt_ms",
                "median_rtt_ms",
                "max_rtt_ms",
                "p95_rtt_ms",
                "jitter_ms",
                "rtt_samples_ms",
            ],
        ),
        "http": (
            "http_results",
            [
                "method",
                "scheme",
                "status_code",
                "redirect_count",
                "response_size_bytes",
                "dns_ms",
                "connect_ms",
                "tls_ms",
                "ttfb_ms",
                "total_ms",
                "assertions_total",
                "assertions_failed",
                "final_url_redacted",
            ],
        ),
        "tcp": ("tcp_results", ["port", "address_used", "connect_ms"]),
        "dns": (
            "dns_results",
            [
                "resolver_address",
                "query_name",
                "query_type",
                "response_code",
                "response_ms",
                "answer_count",
                "answers",
                "truncated",
                "authoritative",
                "assertions_total",
                "assertions_failed",
            ],
        ),
        "tls": (
            "tls_results",
            [
                "port",
                "server_name",
                "protocol_version",
                "cipher_suite",
                "handshake_ms",
                "certificate_present",
                "hostname_valid",
                "chain_valid",
                "not_before",
                "not_after",
                "days_remaining",
                "subject_name",
                "issuer_name",
                "serial_number",
                "fingerprint_sha256",
            ],
        ),
    }
    table, columns = specifications[observation.probe_type]
    values = identity + [
        json.dumps(data[column]) if column == "answers" else data[column] for column in columns
    ]
    all_columns = ["scheduled_at", "observation_id", "realm_id", "agent_id", "monitor_id", *columns]
    placeholders = ", ".join(f"${index}" for index in range(1, len(values) + 1))
    # Table and column identifiers come exclusively from the static specification
    # above; every observation-provided value remains parameterized.
    query = f"INSERT INTO {table} ({', '.join(all_columns)}) VALUES ({placeholders})"  # noqa: S608
    await connection.execute_query(
        query,
        values,
    )


async def ingest_observations(
    *, authentication: AgentAuthentication, upload: AgentObservationUpload
) -> list[AgentObservationResult]:
    snapshot = await AgentConfigurationSnapshot.filter(
        realm=authentication.realm,
        agent=authentication.agent,
        revision=upload.agent_config_revision,
    ).first()
    if snapshot is None:
        return [
            _rejected(observation, "configuration_revision_unavailable", retryable=True)
            for observation in upload.observations
        ]
    configured = {monitor["monitor_id"]: monitor for monitor in snapshot.configuration["monitors"]}
    now = datetime.now(UTC)
    results: list[AgentObservationResult] = []
    async with in_transaction() as connection:
        for observation in upload.observations:
            monitor = configured.get(str(observation.monitor_id))
            if monitor is None or monitor.get("probe_type") != observation.probe_type:
                results.append(_rejected(observation, "monitor_not_in_configuration"))
                continue
            if monitor.get("monitor_revision") != observation.monitor_revision:
                results.append(_rejected(observation, "monitor_revision_mismatch"))
                continue
            if observation.scheduled_at < now - MAXIMUM_OBSERVATION_AGE:
                results.append(_rejected(observation, "observation_too_old"))
                continue
            if observation.scheduled_at > now + MAXIMUM_FUTURE_SKEW:
                results.append(_rejected(observation, "observation_in_future"))
                continue
            content_hash = _canonical_hash(observation)
            inserted = await _insert_common(
                connection, authentication, upload, observation, content_hash
            )
            if not inserted:
                existing_hash = await _existing_hash(connection, observation)
                disposition: Literal["duplicate", "rejected"] = (
                    "duplicate" if existing_hash == content_hash else "rejected"
                )
                results.append(
                    AgentObservationResult(
                        scheduled_at=observation.scheduled_at,
                        observation_id=observation.observation_id,
                        disposition=disposition,
                        code=None if disposition == "duplicate" else "idempotency_conflict",
                    )
                )
                continue
            await _insert_typed_result(connection, authentication, observation)
            results.append(
                AgentObservationResult(
                    scheduled_at=observation.scheduled_at,
                    observation_id=observation.observation_id,
                    disposition="accepted",
                )
            )
    return results
