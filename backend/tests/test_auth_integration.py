from collections.abc import Iterator
from uuid import uuid4
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from backend.app.db.database import SessionLocal
from backend.app.db.models import SecurityEvent, User, UserRole
from backend.app.security.passwords import verify_password
from backend.app.security.tokens import ALGORITHM, decode_access_token
from backend.app.config import get_settings


TEST_PASSWORD = "integration-test-password"


@pytest.fixture
def unique_username() -> Iterator[str]:
    username = f"test-{uuid4().hex}" # each test is unique
    unknown_username = f"unknown-{username}"

    yield username

    with SessionLocal() as database_session:
        database_session.execute(
            delete(SecurityEvent).where(
                SecurityEvent.actor_username.in_(
                    [
                        username,
                        unknown_username,
                    ]
                )
            )
        )
        database_session.execute(delete(User).where(User.username == username))
        database_session.commit()

def register_integration_user(client: TestClient, username: str) -> dict[str, object]:
    response = client.post(
        "/auth/register",
        json={"username": username, "password": TEST_PASSWORD}
    )
    assert response.status_code == 201
    return response.json()

def login_integration_user(client: TestClient, username: str,) -> str:
    response = client.post(
        "/auth/login",
        data={
            "username": username,
            "password": TEST_PASSWORD
        }
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["token_type"] == "bearer"
    return response_data["access_token"]


# TestClient request -> UserRegistration -> register_user -> SQLAlchemy/PostgreSQL -> UserResponse -> Test Queries
@pytest.mark.integration
def test_registration_persists_argon2_hash_in_postgresql(client: TestClient, unique_username: str) -> None:
    response = client.post(
        "/auth/register",
        json={
            "username": f"  {unique_username.upper()}  ",
            "password": TEST_PASSWORD
        }
    )

    assert response.status_code == 201

    response_data = response.json()

    assert response_data["username"] == unique_username
    assert "password" not in response_data
    assert "password_hash" not in response_data

    with SessionLocal() as database_session:
        stored_user = database_session.scalar(
            select(User).where(
                User.username == unique_username
            )
        )
        assert stored_user is not None
        assert str(stored_user.id) == response_data["id"]
        assert stored_user.username == unique_username
        assert stored_user.password_hash != TEST_PASSWORD
        assert stored_user.password_hash.startswith("$argon2id$")
        assert verify_password(TEST_PASSWORD, stored_user.password_hash)
        assert stored_user.role == UserRole.USER.value
        assert response_data["role"] == "user"


@pytest.mark.integration
def test_postgresql_rejects_duplicate_usernames(unique_username: str) -> None:
    with SessionLocal() as database_session:
        first_user = User(
            username=unique_username,
            password_hash="$argon2id$first-test-hash"
        )
        database_session.add(first_user)
        database_session.commit()

        duplicate_user = User(
            username=unique_username,
            password_hash="$argon2id$second-test-hash"
        )
        database_session.add(duplicate_user)

        with pytest.raises(IntegrityError):
            database_session.commit()

        database_session.rollback()


@pytest.mark.integration
def test_login_returns_valid_jwt_for_registered_user(client: TestClient, unique_username: str) -> None:
    registration_data = register_integration_user(client, unique_username)

    response = client.post(
        "/auth/login",
        data={
            "username": f"  {unique_username.upper()}  ",
            "password": TEST_PASSWORD,
        }
    )

    assert response.status_code == 200

    response_data = response.json()

    assert response_data["token_type"] == "bearer"
    assert isinstance(response_data["access_token"], str)
    assert response_data["access_token"]

    token_user_id = decode_access_token(response_data["access_token"])

    assert str(token_user_id) == registration_data["id"]


@pytest.mark.integration
def test_wrong_password_and_unknown_username_have_same_response(client: TestClient, unique_username: str) -> None:
    register_integration_user(client, unique_username)

    wrong_password_response = client.post(
        "/auth/login",
        data={
            "username": unique_username,
            "password": "incorrect-password",
        },
    )

    unknown_username = f"unknown-{unique_username}"

    unknown_user_response = client.post(
        "/auth/login",
        data={
            "username": unknown_username,
            "password": "incorrect-password",
        },
    )

    expected_response = {"detail": "Incorrect username or password"}

    assert wrong_password_response.status_code == 401
    assert unknown_user_response.status_code == 401
    assert wrong_password_response.json() == expected_response
    assert unknown_user_response.json() == expected_response
    assert (wrong_password_response.headers["www-authenticate"] == "Bearer")
    assert (unknown_user_response.headers["www-authenticate"] == "Bearer")


@pytest.mark.integration
def test_inactive_user_cannot_log_in(client: TestClient, unique_username: str) -> None:
    register_integration_user(client, unique_username)

    with SessionLocal() as database_session:
        stored_user = database_session.scalar(
            select(User).where(
                User.username == unique_username
            )
        )

        assert stored_user is not None

        stored_user.is_active = False
        database_session.commit()

    response = client.post(
        "/auth/login",
        data={
            "username": unique_username,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.integration
def test_me_returns_user_for_valid_bearer_token(client: TestClient, unique_username: str) -> None:
    registration_data = register_integration_user(client, unique_username)
    access_token = login_integration_user(client, unique_username)

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200

    response_data = response.json()

    assert response_data["id"] == registration_data["id"]
    assert response_data["username"] == unique_username
    assert response_data["role"] == "user"
    assert response_data["is_active"] is True
    assert "created_at" in response_data
    assert set(response_data) == {
        "id",
        "username",
        "role",
        "is_active",
        "created_at",
    }


@pytest.mark.integration
def test_me_rejects_token_after_user_is_disabled(client: TestClient, unique_username: str) -> None:
    register_integration_user(client, unique_username)
    access_token = login_integration_user(client, unique_username)

    # disable the user in PostgreSQL
    with SessionLocal() as database_session:
        stored_user = database_session.scalar(
            select(User).where(
                User.username == unique_username
            )
        )

        assert stored_user is not None

        stored_user.is_active = False
        database_session.commit()

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.integration
def test_me_rejects_token_after_user_is_deleted(client: TestClient, unique_username: str) -> None:
    register_integration_user(client, unique_username)
    access_token = login_integration_user(client, unique_username)

    with SessionLocal() as database_session:
        database_session.execute(
            delete(User).where(
                User.username == unique_username
            )
        )
        database_session.commit()

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.integration
def test_me_rejects_expired_token_for_existing_user(client: TestClient, unique_username: str) -> None:
    registration_data = register_integration_user(client, unique_username)
    settings = get_settings()
    current_time = datetime.now(timezone.utc)

    expired_token = jwt.encode(
        {
            "sub": registration_data["id"],
            "iat": current_time - timedelta(minutes=2),
            "exp": current_time - timedelta(minutes=1)
        },
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.integration
def test_postgresql_rejects_invalid_user_role(unique_username: str) -> None:
    with SessionLocal() as database_session:
        invalid_user = User(
            username=unique_username,
            password_hash="$argon2id$test-password-hash",
            role="superadmin"
        )
        database_session.add(invalid_user)

        with pytest.raises(IntegrityError):
            database_session.commit()

        database_session.rollback()


# Client should not be able to create admin role
@pytest.mark.integration
def test_registration_rejects_client_supplied_admin_role(client: TestClient, unique_username: str) -> None:
    response = client.post(
        "/auth/register",
        json={
            "username": unique_username,
            "password": TEST_PASSWORD,
            "role": "admin"
        }
    )

    assert response.status_code == 422

    with SessionLocal() as database_session: 
        stored_user = database_session.scalar(
            select(User).where(
                User.username == unique_username
            )
        )
        assert stored_user is None
