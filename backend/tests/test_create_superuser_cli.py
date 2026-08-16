from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bifrostnms.cli.create_superuser import ensure_initial_realm
from bifrostnms.models import Realm


@pytest.mark.asyncio
async def test_ensure_initial_realm_reuses_existing_active_realm() -> None:
    realm = cast(Realm, SimpleNamespace(name="Existing", slug="existing"))
    query = MagicMock()
    query.order_by.return_value = query
    query.first = AsyncMock(return_value=realm)

    with (
        patch("bifrostnms.cli.create_superuser.Realm.filter", return_value=query),
        patch("bifrostnms.cli.create_superuser.Realm.create", new=AsyncMock()) as create,
    ):
        result = await ensure_initial_realm("Default")

    assert result is realm
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_initial_realm_creates_realm_when_none_are_active() -> None:
    realm = cast(Realm, SimpleNamespace(name="Local Lab", slug="local-lab"))
    active_query = MagicMock()
    active_query.order_by.return_value = active_query
    active_query.first = AsyncMock(return_value=None)
    slug_query = MagicMock()
    slug_query.exists = AsyncMock(return_value=False)
    create = AsyncMock(return_value=realm)

    with (
        patch(
            "bifrostnms.cli.create_superuser.Realm.filter",
            side_effect=[active_query, slug_query],
        ),
        patch("bifrostnms.cli.create_superuser.Realm.create", new=create),
    ):
        result = await ensure_initial_realm(" Local Lab ")

    assert result is realm
    create.assert_awaited_once_with(name="Local Lab", slug="local-lab", is_active=True)
