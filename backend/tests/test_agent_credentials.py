from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Request
from tortoise import Tortoise

from bifrostnms.agents import (
    AgentProtocolError,
    EnrolmentError,
    authenticate_agent,
    exchange_enrolment_token,
    issue_enrolment_token,
    require_supported_protocol,
    revoke_credential,
    revoke_enrolment_token,
)
from bifrostnms.auth.security import hash_token
from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import (
    Agent,
    AgentCredential,
    AgentEnrolmentToken,
    AgentOperationalState,
    Realm,
)


def request(credential: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/agent/heartbeat",
            "headers": [(b"authorization", f"Bearer {credential}".encode())],
        }
    )


@pytest_asyncio.fixture
async def enrolled_agent() -> AsyncIterator[tuple[Realm, Agent]]:
    await Tortoise.init(config=TORTOISE_ORM)
    realm = await Realm.create(name="Agents", slug=f"agents-{uuid4().hex}")
    agent = await Agent.create(realm=realm, name="London")
    try:
        yield realm, agent
    finally:
        await AgentEnrolmentToken.filter(realm=realm).delete()
        await AgentCredential.filter(realm=realm).delete()
        await AgentOperationalState.filter(realm=realm).delete()
        await agent.delete()
        await realm.delete()
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_enrolment_token_is_stored_as_a_digest_and_consumed_once(
    enrolled_agent: tuple[Realm, Agent],
) -> None:
    realm, agent = enrolled_agent
    token, raw_token = await issue_enrolment_token(realm=realm, agent=agent)

    assert token.token_hash == hash_token(raw_token)
    assert raw_token != token.token_hash

    enrolled, credential, raw_credential = await exchange_enrolment_token(raw_token)
    assert enrolled.id == agent.id
    assert raw_credential.startswith(f"{credential.id}.")
    assert credential.credential_hash not in raw_credential

    with pytest.raises(EnrolmentError, match="invalid or expired"):
        await exchange_enrolment_token(raw_token)


@pytest.mark.asyncio
async def test_new_enrolment_token_revokes_the_previous_token(
    enrolled_agent: tuple[Realm, Agent],
) -> None:
    realm, agent = enrolled_agent
    previous, previous_raw = await issue_enrolment_token(realm=realm, agent=agent)
    _, current_raw = await issue_enrolment_token(realm=realm, agent=agent)
    await previous.refresh_from_db()

    assert previous.revoked_at is not None
    with pytest.raises(EnrolmentError):
        await exchange_enrolment_token(previous_raw)
    assert (await exchange_enrolment_token(current_raw))[0].id == agent.id


@pytest.mark.asyncio
async def test_enrolment_token_exchange_is_atomic(
    enrolled_agent: tuple[Realm, Agent],
) -> None:
    realm, agent = enrolled_agent
    _, raw_token = await issue_enrolment_token(realm=realm, agent=agent)

    results = await asyncio.gather(
        exchange_enrolment_token(raw_token),
        exchange_enrolment_token(raw_token),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, EnrolmentError) for result in results) == 1
    assert await AgentCredential.filter(realm=realm, agent=agent).count() == 1


@pytest.mark.asyncio
async def test_expired_or_revoked_enrolment_token_cannot_be_used(
    enrolled_agent: tuple[Realm, Agent],
) -> None:
    realm, agent = enrolled_agent
    expired, expired_raw = await issue_enrolment_token(
        realm=realm, agent=agent, ttl=timedelta(seconds=-1)
    )
    with pytest.raises(EnrolmentError):
        await exchange_enrolment_token(expired_raw)

    active, active_raw = await issue_enrolment_token(realm=realm, agent=agent)
    assert await revoke_enrolment_token(realm=realm, agent=agent, token_id=active.id)
    with pytest.raises(EnrolmentError):
        await exchange_enrolment_token(active_raw)
    assert expired.expires_at < datetime.now(UTC)


@pytest.mark.asyncio
async def test_agent_credential_authentication_and_revocation(
    enrolled_agent: tuple[Realm, Agent],
) -> None:
    realm, agent = enrolled_agent
    _, raw_token = await issue_enrolment_token(realm=realm, agent=agent)
    _, credential, raw_credential = await exchange_enrolment_token(raw_token)

    authentication = await authenticate_agent(request(raw_credential))
    assert authentication.agent.id == agent.id
    assert authentication.realm.id == realm.id
    await credential.refresh_from_db()
    assert credential.last_used_at is not None

    assert await revoke_credential(realm=realm, credential_id=credential.id)
    with pytest.raises(AgentProtocolError) as exc:
        await authenticate_agent(request(raw_credential))
    assert exc.value.status_code == 401
    assert exc.value.code == "invalid_credential"


@pytest.mark.asyncio
async def test_credential_cannot_cross_agent_or_realm_boundaries(
    enrolled_agent: tuple[Realm, Agent],
) -> None:
    realm, agent = enrolled_agent
    other_realm = await Realm.create(name="Other", slug=f"other-{uuid4().hex}")
    other_agent = await Agent.create(realm=other_realm, name="Remote")
    try:
        token, raw_token = await issue_enrolment_token(realm=realm, agent=agent)
        assert not await revoke_enrolment_token(
            realm=other_realm, agent=other_agent, token_id=token.id
        )
        _, credential, _ = await exchange_enrolment_token(raw_token)
        assert not await revoke_credential(realm=other_realm, credential_id=credential.id)
    finally:
        await AgentEnrolmentToken.filter(realm=other_realm).delete()
        await AgentCredential.filter(realm=other_realm).delete()
        await other_agent.delete()
        await other_realm.delete()


def test_protocol_version_range_is_explicit() -> None:
    require_supported_protocol(1)
    with pytest.raises(AgentProtocolError) as exc:
        require_supported_protocol(2)
    assert exc.value.code == "incompatible_protocol"
    assert exc.value.retryable is False
    assert exc.value.details == {
        "minimum_protocol_version": 1,
        "maximum_protocol_version": 1,
    }
