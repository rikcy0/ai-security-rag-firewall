from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.db.models import User
from backend.app.security import authentication
from backend.app.security.tokens import AccessTokenError


TEST_TOKEN = "signed-access-token"
PASSWORD_HASH = "$argon2id$test-password-hash"


def make_user(user_id: UUID, is_active: bool = True) -> User:
    user = User(
        username="alice",
        password_hash=PASSWORD_HASH,
        is_active=is_active,
    )
    user.id = user_id

    return user


def assert_authentication_error(exception: HTTPException) -> None:
    assert exception.status_code == 401
    assert exception.detail == "Could not validate credentials"
    assert exception.headers == {
        "WWW-Authenticate": "Bearer"
    }


def test_get_current_user_returns_active_user(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    user_id = uuid4()
    expected_user = make_user(user_id)

    token_decoder = Mock(return_value=user_id)
    user_lookup = Mock(return_value=expected_user)

    monkeypatch.setattr(
        authentication,
        "decode_access_token",
        token_decoder
    )
    monkeypatch.setattr(
        authentication,
        "get_user_by_id",
        user_lookup
    )

    result = authentication.get_current_user(
        TEST_TOKEN,
        database_session
    )

    assert result is expected_user
    token_decoder.assert_called_once_with(TEST_TOKEN)
    user_lookup.assert_called_once_with(database_session, user_id)


def test_get_current_user_rejects_missing_token(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    token_decoder = Mock()
    user_lookup = Mock()

    monkeypatch.setattr(
        authentication,
        "decode_access_token",
        token_decoder
    )
    monkeypatch.setattr(
        authentication,
        "get_user_by_id",
        user_lookup
    )

    with pytest.raises(HTTPException) as exc_info:
        authentication.get_current_user(None, database_session)

    assert_authentication_error(exc_info.value)
    # no reason to decode or query PostgreSQL if no token is supplied
    token_decoder.assert_not_called()
    user_lookup.assert_not_called()


def test_get_current_user_rejects_invalid_token(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    token_decoder = Mock(
        side_effect=AccessTokenError("Invalid or expired access token")
    )
    user_lookup = Mock()

    monkeypatch.setattr(
        authentication,
        "decode_access_token",
        token_decoder
    )
    monkeypatch.setattr(
        authentication,
        "get_user_by_id",
        user_lookup
    )

    with pytest.raises(HTTPException) as exc_info:
        authentication.get_current_user(TEST_TOKEN, database_session)

    assert_authentication_error(exc_info.value)
    token_decoder.assert_called_once_with(TEST_TOKEN)
    user_lookup.assert_not_called()


def test_get_current_user_rejects_missing_user(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    user_id = uuid4()

    monkeypatch.setattr(
        authentication,
        "decode_access_token",
        Mock(return_value=user_id)
    )
    monkeypatch.setattr(
        authentication,
        "get_user_by_id",
        Mock(return_value=None)
    )

    with pytest.raises(HTTPException) as exc_info:
        authentication.get_current_user(TEST_TOKEN, database_session)

    assert_authentication_error(exc_info.value)


def test_get_current_user_rejects_inactive_user(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    user_id = uuid4()

    monkeypatch.setattr(
        authentication,
        "decode_access_token",
        Mock(return_value=user_id)
    )
    monkeypatch.setattr(
        authentication,
        "get_user_by_id",
        Mock(
            return_value=make_user(user_id, is_active=False)
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        authentication.get_current_user(TEST_TOKEN, database_session)

    assert_authentication_error(exc_info.value)