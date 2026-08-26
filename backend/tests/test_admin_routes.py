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
from backend.app.security import access_control
from backend.app.db.models import SecurityEvent, SecurityEventType, User, UserRole


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

def make_security_event(actor_user: User) -> SecurityEvent:
    event = SecurityEvent(
        event_type=(
            SecurityEventType.AUTHORIZATION_DENIED.value
        ),
        actor_user_id=actor_user.id,
        actor_username=actor_user.username,
        details={
            "required_role": "admin",
            "actual_role": "user",
        },
    )

    event.id = uuid4()
    event.created_at = datetime(
        2026,
        1,
        2,
        tzinfo=timezone.utc,
    )

    return event


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
    audit_recorder = Mock()

    monkeypatch.setattr(
        admin_routes,
        "list_users",
        user_listing,
    )
    monkeypatch.setattr(
        access_control,
        "record_authorization_denial",
        audit_recorder,
    )

    response = client.get("/admin/users")

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}
    assert "www-authenticate" not in response.headers

    user_listing.assert_not_called()

    audit_recorder.assert_called_once_with(
        actor_user_id=ordinary_user.id,
        actor_username=ordinary_user.username,
        required_role=UserRole.ADMIN,
        actual_role=UserRole.USER.value,
    )


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


def test_admin_can_list_security_events(
    client: TestClient,
    database_session: Mock,
    admin_user: User,
    monkeypatch
) -> None:
    event = make_security_event(admin_user)
    event_listing = Mock(
        return_value=[event]
    )

    monkeypatch.setattr(
        admin_routes,
        "list_security_events",
        event_listing,
    )

    response = client.get(
        "/admin/security-events?limit=1"
    )

    assert response.status_code == 200

    response_data = response.json()

    assert response_data == [
        {
            "id": str(event.id),
            "event_type": "authorization_denied",
            "actor_user_id": str(admin_user.id),
            "actor_username": admin_user.username,
            "details": {
                "required_role": "admin",
                "actual_role": "user",
            },
            "created_at": "2026-01-02T00:00:00Z",
        }
    ]

    event_listing.assert_called_once_with(
        database_session,
        limit=1,
    )


def test_security_event_listing_uses_default_limit(
    client: TestClient,
    database_session: Mock,
    admin_user: User,
    monkeypatch
) -> None:
    event_listing = Mock(return_value=[])

    monkeypatch.setattr(
        admin_routes,
        "list_security_events",
        event_listing,
    )

    response = client.get("/admin/security-events")

    assert response.status_code == 200
    assert response.json() == []

    event_listing.assert_called_once_with(
        database_session,
        limit=50,
    )


@pytest.mark.parametrize(
    "invalid_limit",
    [
        0,
        101,
    ],
)
def test_security_event_listing_rejects_invalid_limit(
    client: TestClient,
    database_session: Mock,
    admin_user: User,
    invalid_limit: int,
    monkeypatch
) -> None:
    event_listing = Mock()

    monkeypatch.setattr(
        admin_routes,
        "list_security_events",
        event_listing,
    )

    response = client.get(
        f"/admin/security-events?limit={invalid_limit}"
    )

    assert response.status_code == 422
    event_listing.assert_not_called()


def test_ordinary_user_cannot_list_security_events(
    client: TestClient,
    ordinary_user: User,
    monkeypatch
) -> None:
    event_listing = Mock()
    audit_recorder = Mock()

    monkeypatch.setattr(
        admin_routes,
        "list_security_events",
        event_listing,
    )
    monkeypatch.setattr(
        access_control,
        "record_authorization_denial",
        audit_recorder,
    )

    response = client.get("/admin/security-events")

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Insufficient permissions"
    }

    event_listing.assert_not_called()

    audit_recorder.assert_called_once_with(
        actor_user_id=ordinary_user.id,
        actor_username=ordinary_user.username,
        required_role=UserRole.ADMIN,
        actual_role=UserRole.USER.value,
    )


def test_security_event_listing_requires_authentication(
    client: TestClient,
    monkeypatch
) -> None:
    event_listing = Mock()

    monkeypatch.setattr(
        admin_routes,
        "list_security_events",
        event_listing,
    )

    response = client.get("/admin/security-events")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials"
    }
    assert response.headers["www-authenticate"] == "Bearer"

    event_listing.assert_not_called()