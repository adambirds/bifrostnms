import re

from bifrostnms.auth.two_factor import (
    RECOVERY_CODE_COUNT,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_code,
    hash_recovery_code,
)


def test_totp_secret_encryption_round_trip():
    secret = "JBSWY3DPEHPK3PXP"
    encrypted = encrypt_secret(secret)

    assert encrypted != secret
    assert decrypt_secret(encrypted) == secret


def test_recovery_code_hash_is_normalized():
    expected = hash_recovery_code("ABCD-EFGH-IJKL")

    assert hash_recovery_code(" abcd-efgh-ijkl ") == expected
    assert hash_recovery_code("ABCD-EFGH-IJKL") != hash_recovery_code("ABCD-EFGH-IJKM")


def test_generated_recovery_code_format_and_uniqueness():
    codes = {generate_recovery_code() for _ in range(RECOVERY_CODE_COUNT)}

    assert len(codes) == RECOVERY_CODE_COUNT
    assert all(re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", code) for code in codes)
    assert all(
        "0" not in code and "1" not in code and "I" not in code and "O" not in code
        for code in codes
    )
