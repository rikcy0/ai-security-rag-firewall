from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import User, UserRole
from backend.app.main import app
from backend.app.routes import admin_routes
from backend.app.security.authentication import get_current_user


PASSWORD_HASH = "$argon2id$test-password-hash"


def make_user(username: str, role: UserRole) -> User:
    user = User(
        username=username,
        password_hash=PASSWORD_HASH,
        role=role.value,
        is_active=True
    )
    user.id = uuid4()
    user.created_at = datetime(
        2026,
        1,
        1,
        tzinfo=timezone.utc
    )

    return user


@pytest.fixture
def database_session():
    session = Mock(spec=Session)
    app.dependency_overrides[get_db] = (lambda: session)
    yield session
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture
def admin_user():
    user = make_user("admin", UserRole.ADMIN)
    app.dependency_overrides[get_current_user] = (lambda: user)
    yield user
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture
def ordinary_user():
    user = make_user("alice", UserRole.USER)
    app.dependency_overrides[get_current_user] = (lambda: user)
    yield user
    app.dependency_overrides.pop(get_current_user, None)


def test_admin_can_list_safe_user_records(client: TestClient, database_session: Mock, admin_user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    ordinary_user = make_user("alice", UserRole.USER)
    user_listing = Mock(
        return_value=[
            admin_user,
            ordinary_user
        ]
    )
    monkeypatch.setattr(
        admin_routes,
        "list_users",
        user_listing
    )

    response = client.get("/admin/users")

    assert response.status_code == 200

    response_data = response.json()

    assert len(response_data) == 2
    assert response_data[0]["username"] == "admin"
    assert response_data[0]["role"] == "admin"
    assert response_data[1]["username"] == "alice"
    assert response_data[1]["role"] == "user"

    for user_data in response_data:
        assert set(user_data) == {
            "id",
            "username",
            "role",
            "is_active",
            "created_at"
        }
        assert "password_hash" not in user_data

    user_listing.assert_called_once_with(database_session)


def test_ordinary_user_cannot_list_users(client, ordinary_user, monkeypatch) -> None:
    user_listing = Mock()

    monkeypatch.setattr(
        admin_routes,
        "list_users",
        user_listing,
    )

    response = client.get("/admin/users")

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}
    assert "www-authenticate" not in response.headers
    user_listing.assert_not_called()


def test_admin_users_requires_authentication(client, monkeypatch) -> None:
    user_listing = Mock()

    monkeypatch.setattr(
        admin_routes,
        "list_users",
        user_listing
    )

    response = client.get("/admin/users")

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"
    user_listing.assert_not_called()