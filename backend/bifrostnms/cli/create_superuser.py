from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from tortoise import Tortoise

from bifrostnms.auth.security import hash_password, normalize_email
from bifrostnms.database import TORTOISE_ORM
from bifrostnms.models import User


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or promote a BifrostNMS installation superuser.",
    )
    parser.add_argument("--email", help="Email address for the superuser")
    parser.add_argument("--first-name", help="First name")
    parser.add_argument("--last-name", help="Last name")
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


def _read_password() -> str:
    env_password = os.getenv("BIFROSTNMS_SUPERUSER_PASSWORD")
    if env_password:
        return env_password

    while True:
        password = getpass.getpass("Password: ")
        if len(password) < 12:
            print("Password must be at least 12 characters.", file=sys.stderr)
            continue
        confirmation = getpass.getpass("Password (again): ")
        if password != confirmation:
            print("Passwords do not match.", file=sys.stderr)
            continue
        return password


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
