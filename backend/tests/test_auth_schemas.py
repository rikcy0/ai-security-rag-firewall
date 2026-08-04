from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.db.models import UserRole
from backend.app.schemas.auth import TokenResponse, UserLogin, UserRegistration, UserResponse


def test_registration_normalizes_username() -> None:
    registration = UserRegistration(
        username="  Alice-Example_1  ",
        password="a-secure-password",
    )

    assert registration.username == "alice-example_1"


@pytest.mark.parametrize(
    "username",
    [
        "ab",
        "a" * 51,
        "contains spaces",
        "invalid!",
        "   ",
    ],
)
def test_registration_rejects_invalid_usernames(username: str) -> None:
    with pytest.raises(ValidationError):
        UserRegistration(
            username=username,
            password="a-secure-password",
        )


def test_registration_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        UserRegistration(
            username="alice",
            password="a" * 14,
        )


def test_registration_rejects_oversized_password() -> None:
    with pytest.raises(ValidationError):
        UserRegistration(
            username="alice",
            password="a" * 129,
        )


def test_login_accepts_nonempty_password_below_registration_minimum() -> None:
    login = UserLogin(
        username="alice",
        password="wrong",
    )

    assert login.password.get_secret_value() == "wrong"


def test_password_is_hidden_in_schema_representation() -> None:
    plaintext_password = "a-secure-password"
    registration = UserRegistration(
        username="alice",
        password=plaintext_password,
    )

    assert plaintext_password not in repr(registration)


def test_user_response_excludes_password_hash() -> None:
    password_hash = "$argon2id$private-hash"
    database_user = SimpleNamespace(
        id=uuid4(),
        username="alice",
        role=UserRole.USER.value,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        password_hash=password_hash,
    )
    response = UserResponse.model_validate(database_user)
    response_data = response.model_dump()

    assert response.username == "alice"
    assert "password" not in response_data
    assert "password_hash" not in response_data
    assert password_hash not in repr(response)
    assert response.role is UserRole.USER
    assert response.model_dump(mode="json")["role"] == "user"


def test_token_response_defaults_to_bearer() -> None:
    response = TokenResponse(access_token="signed-jwt")

    assert response.access_token == "signed-jwt"
    assert response.token_type == "bearer"


def test_registration_rejects_client_supplied_role() -> None:
    with pytest.raises(ValidationError):
        UserRegistration.model_validate(
            {
                "username": "alice",
                "password": "a-secure-password",
                "role": "admin",
            }
        )


def test_user_response_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError):
        UserResponse(
            id=uuid4(),
            username="alice",
            role="superadmin", # rejected by UserResponse validation
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )