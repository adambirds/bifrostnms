import os

from bifrostnms.auth.webauthn import _b64, _unb64


def test_webauthn_base64url_round_trip() -> None:
    data = os.urandom(64)
    encoded = _b64(data)

    assert "=" not in encoded
    assert _unb64(encoded) == data


def test_webauthn_base64url_handles_padding() -> None:
    assert _unb64(_b64(b"abc")) == b"abc"
    assert _unb64(_b64(b"abcd")) == b"abcd"
