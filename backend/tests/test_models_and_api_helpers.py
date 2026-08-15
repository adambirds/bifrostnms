from bifrostnms.api.auth import slugify
from bifrostnms.models import User


def test_slugify_normalizes_realm_names():
    assert slugify("My Home Lab") == "my-home-lab"
    assert slugify("  ADB Software & Solutions  ") == "adb-software-solutions"
    assert slugify("***") == "realm"


def test_user_full_name():
    user = User(
        email="adam@example.com",
        password_hash="hash",
        first_name="Adam",
        last_name="Birds",
    )
    assert user.full_name == "Adam Birds"


def test_user_full_name_does_not_leave_extra_whitespace():
    user = User(
        email="adam@example.com",
        password_hash="hash",
        first_name="Adam",
        last_name="",
    )
    assert user.full_name == "Adam"
