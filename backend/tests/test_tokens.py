from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from backend.app.config import get_settings
from backend.app.security.tokens import (AccessTokenError, create_access_token, decode_access_token)


TEST_SECRET_KEY = "test-jwt-secret-key-" * 2
WRONG_SECRET_KEY = "different-test-secret-key-" * 2


@pytest.fixture(autouse=True)
def configure_token_settings(monkeypatch):
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_SECRET_KEY",
        TEST_SECRET_KEY
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_ACCESS_TOKEN_EXPIRE_MINUTES",
        "60"
    )

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_valid_payload(subject: str) -> dict[str, object]:
    issued_at = datetime.now(timezone.utc)

    return {
        "sub": subject,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=60)
    }


def encode_test_token(
    payload: dict[str, object],
    secret_key: str = TEST_SECRET_KEY,
) -> str:
    return jwt.encode(
        payload,
        secret_key,
        algorithm="HS256"
    )


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    token = create_access_token(user_id)
    decoded_user_id = decode_access_token(token)

    assert decoded_user_id == user_id


def test_access_token_contains_expected_claims() -> None:
    user_id = uuid4()

    token = create_access_token(user_id)

    header = jwt.get_unverified_header(token)
    payload = jwt.decode(
        token,
        TEST_SECRET_KEY,
        algorithms=["HS256"]
    )

    assert header["alg"] == "HS256"
    assert payload["sub"] == str(user_id)
    assert "iat" in payload
    assert "exp" in payload
    assert payload["exp"] - payload["iat"] == 60 * 60


def test_expired_access_token_is_rejected() -> None:
    payload = make_valid_payload(str(uuid4()))
    payload["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = encode_test_token(payload)

    with pytest.raises(AccessTokenError):
        decode_access_token(token)


def test_token_signed_with_different_key_is_rejected() -> None:
    payload = make_valid_payload(str(uuid4()))
    token = encode_test_token(payload, secret_key=WRONG_SECRET_KEY)

    with pytest.raises(AccessTokenError):
        decode_access_token(token)


def test_token_without_subject_is_rejected() -> None:
    payload = make_valid_payload(str(uuid4()))
    del payload["sub"]
    token = encode_test_token(payload)

    with pytest.raises(AccessTokenError):
        decode_access_token(token)


def test_token_with_non_uuid_subject_is_rejected() -> None:
    payload = make_valid_payload("not-a-valid-uuid")
    token = encode_test_token(payload)

    with pytest.raises(AccessTokenError):
        decode_access_token(token)


def test_malformed_token_is_rejected() -> None:
    with pytest.raises(AccessTokenError):
        decode_access_token("not-a-jwt")