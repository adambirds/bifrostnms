from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, status
from tortoise.transactions import in_transaction

from bifrostnms.auth.security import hash_token
from bifrostnms.config import get_settings
from bifrostnms.models import Agent, AgentCredential, AgentEnrolmentToken, Realm


class EnrolmentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgentAuthentication:
    realm: Realm
    agent: Agent
    credential: AgentCredential


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


async def issue_enrolment_token(
    *, realm: Realm, agent: Agent, ttl: timedelta | None = None
) -> tuple[AgentEnrolmentToken, str]:
    now = datetime.now(UTC)
    raw_token = _new_secret()
    expires_at = now + (ttl or timedelta(minutes=get_settings().agent_enrolment_ttl_minutes))
    async with in_transaction() as connection:
        # Serialize replacement for one agent so concurrent issuers cannot both
        # leave an active token behind.
        await Agent.filter(id=agent.id, realm=realm).using_db(connection).select_for_update().get()
        await (
            AgentEnrolmentToken.filter(realm=realm, agent=agent, consumed_at=None, revoked_at=None)
            .using_db(connection)
            .update(revoked_at=now)
        )
        token = await AgentEnrolmentToken.create(
            realm=realm,
            agent=agent,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
            using_db=connection,
        )
    return token, raw_token


async def exchange_enrolment_token(raw_token: str) -> tuple[Agent, AgentCredential, str]:
    now = datetime.now(UTC)
    async with in_transaction() as connection:
        token = (
            await AgentEnrolmentToken.filter(token_hash=hash_token(raw_token))
            .using_db(connection)
            .select_for_update()
            .first()
        )
        if (
            token is None
            or token.consumed_at is not None
            or token.revoked_at is not None
            or token.expires_at <= now
        ):
            raise EnrolmentError("Enrolment token is invalid or expired")

        agent = (
            await Agent.filter(id=token.agent_id, realm_id=token.realm_id)
            .using_db(connection)
            .first()
        )
        if agent is None or not agent.enabled or agent.archived_at is not None:
            raise EnrolmentError("Enrolment token is invalid or expired")

        credential_secret = _new_secret()
        credential_id = uuid4()
        credential = await AgentCredential.create(
            id=credential_id,
            realm_id=token.realm_id,
            agent_id=token.agent_id,
            name=f"Enrolled {credential_id}",
            credential_hash=hash_token(credential_secret),
            using_db=connection,
        )
        token.consumed_at = now
        await token.save(update_fields=["consumed_at"], using_db=connection)

    return agent, credential, f"{credential.id}.{credential_secret}"


async def authenticate_agent(request: Request) -> AgentAuthentication:
    authorization = request.headers.get("authorization", "")
    scheme, separator, raw_credential = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    identifier, separator, secret = raw_credential.partition(".")
    try:
        credential_id = UUID(identifier)
    except ValueError:
        credential_id = None
    credential = (
        await AgentCredential.filter(id=credential_id).select_related("agent", "realm").first()
        if credential_id is not None
        else None
    )
    now = datetime.now(UTC)
    valid = (
        credential is not None
        and bool(separator)
        and secrets.compare_digest(credential.credential_hash, hash_token(secret))
        and credential.revoked_at is None
        and (credential.expires_at is None or credential.expires_at > now)
        and credential.agent.enabled
        and credential.agent.archived_at is None
    )
    if not valid or credential is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credential")
    credential.last_used_at = now
    await credential.save(update_fields=["last_used_at"])
    return AgentAuthentication(
        realm=credential.realm, agent=credential.agent, credential=credential
    )


async def revoke_enrolment_token(*, realm: Realm, agent: Agent, token_id: UUID) -> bool:
    return bool(
        await AgentEnrolmentToken.filter(
            id=token_id, realm=realm, agent=agent, consumed_at=None, revoked_at=None
        ).update(revoked_at=datetime.now(UTC))
    )


async def revoke_credential(*, realm: Realm, credential_id: UUID) -> bool:
    return bool(
        await AgentCredential.filter(id=credential_id, realm=realm, revoked_at=None).update(
            revoked_at=datetime.now(UTC)
        )
    )
