from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import sys

from tortoise import Tortoise

from bifrostnms.auth.security import hash_password, normalize_email
from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import Realm, User

MIN_PASSWORD_LENGTH = 12
DEFAULT_REALM_NAME = "Default"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or promote a BifrostNMS installation superuser.",
    )
    parser.add_argument("--email", help="Email address for the superuser")
    parser.add_argument("--first-name", help="First name")
    parser.add_argument("--last-name", help="Last name")
    parser.add_argument(
        "--realm-name",
        default=DEFAULT_REALM_NAME,
        help=(
            "Name for the initial realm when the installation does not yet have "
            f"an active realm (default: {DEFAULT_REALM_NAME})"
        ),
    )
    parser.add_argument(
        "--promote-existing",
        action="store_true",
        help="Promote an existing user with the supplied email instead of failing",
    )
    return parser


def _prompt(value: str | None, label: str) -> str:
    if value:
        return value.strip()
    while True:
        entered = input(f"{label}: ").strip()
        if entered:
            return entered


def _validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return password


def _read_password() -> str:
    env_password = os.getenv("BIFROSTNMS_SUPERUSER_PASSWORD")
    if env_password:
        return _validate_password(env_password)

    while True:
        password = getpass.getpass("Password: ")
        try:
            _validate_password(password)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            continue
        confirmation = getpass.getpass("Password (again): ")
        if password != confirmation:
            print("Passwords do not match.", file=sys.stderr)
            continue
        return password


def _slugify_realm(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return value or "realm"


async def ensure_initial_realm(realm_name: str) -> Realm:
    existing = await Realm.filter(is_active=True).order_by("created_at").first()
    if existing is not None:
        return existing

    name = realm_name.strip() or DEFAULT_REALM_NAME
    base_slug = _slugify_realm(name)
    slug = base_slug
    counter = 2
    while await Realm.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    realm = await Realm.create(name=name, slug=slug, is_active=True)
    print(f"Created initial realm {realm.name} ({realm.slug}).")
    return realm


async def create_superuser(args: argparse.Namespace) -> int:
    email = normalize_email(_prompt(args.email, "Email"))
    existing = await User.filter(email=email).first()

    if existing:
        if not args.promote_existing:
            print(
                "A user with that email already exists. Use --promote-existing to grant installation superuser access.",
                file=sys.stderr,
            )
            return 1

        existing.is_superuser = True
        existing.is_active = True
        await existing.save(update_fields=["is_superuser", "is_active", "updated_at"])
        await ensure_initial_realm(args.realm_name)
        print(f"Promoted {existing.email} to installation superuser.")
        return 0

    first_name = _prompt(args.first_name, "First name")
    last_name = _prompt(args.last_name, "Last name")
    password = _read_password()

    user = await User.create(
        email=email,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        is_active=True,
        is_superuser=True,
        email_verified=True,
    )
    await ensure_initial_realm(args.realm_name)
    print(f"Created installation superuser {user.email}.")
    return 0


async def async_main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        return await create_superuser(args)
    finally:
        await Tortoise.close_connections()


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
