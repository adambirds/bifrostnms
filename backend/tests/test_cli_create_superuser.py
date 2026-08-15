import pytest

from bifrostnms.cli.create_superuser import MIN_PASSWORD_LENGTH, _validate_password, build_parser


def test_superuser_cli_parser_supports_promotion():
    args = build_parser().parse_args(
        [
            "--email",
            "admin@example.com",
            "--first-name",
            "Admin",
            "--last-name",
            "User",
            "--promote-existing",
        ]
    )

    assert args.email == "admin@example.com"
    assert args.first_name == "Admin"
    assert args.last_name == "User"
    assert args.promote_existing is True


def test_superuser_password_minimum_length():
    valid = "x" * MIN_PASSWORD_LENGTH
    assert _validate_password(valid) == valid

    with pytest.raises(ValueError, match=f"at least {MIN_PASSWORD_LENGTH} characters"):
        _validate_password("x" * (MIN_PASSWORD_LENGTH - 1))
