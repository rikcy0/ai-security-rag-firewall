from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.main import app
from backend.app.routes import auth_routes
from backend.app.services.auth import UsernameAlreadyExistsError


PLAINTEXT_PASSWORD = "a-secure-password"
PASSWORD_HASH = "$argon2id$test-password-hash"


@pytest.fixture
def database_session():
    session = Mock(spec=Session)
    app.dependency_overrides[get_db] = lambda: session
    yield session
    app.dependency_overrides.pop(get_db, None)


def make_database_user() -> User:
    user = User(
        username="alice",
        password_hash=PASSWORD_HASH
    )
    user.id = uuid4()
    user.is_active = True
    user.created_at = datetime(
        2026,
        1,
        1,
        tzinfo=timezone.utc
    )
    return user


def test_register_returns_created_user(client: TestClient, database_session: Mock, monkeypatch) -> None:
    database_user = make_database_user()
    registration_service = Mock(return_value=database_user)

    monkeypatch.setattr(
        auth_routes,
        "register_user",
        registration_service
    )

    response = client.post(
        "/auth/register",
        json={
            "username": "  Alice  ",
            "password": PLAINTEXT_PASSWORD
        }
    )

    assert response.status_code == 201

    response_data = response.json()

    assert response_data["id"] == str(database_user.id)
    assert response_data["username"] == "alice"
    assert response_data["is_active"] is True
    assert "created_at" in response_data
    assert "password" not in response_data
    assert "password_hash" not in response_data

    called_session, registration = (registration_service.call_args.args)

    assert called_session is database_session
    assert registration.username == "alice"
    assert registration.password.get_secret_value() == PLAINTEXT_PASSWORD
    


def test_register_returns_conflict_for_duplicate_username(client, database_session, monkeypatch) -> None:
    registration_service = Mock(side_effect=UsernameAlreadyExistsError("Internal duplicate error"))

    monkeypatch.setattr(
        auth_routes,
        "register_user",
        registration_service
    )

    response = client.post(
        "/auth/register",
        json={
            "username": "alice",
            "password": PLAINTEXT_PASSWORD,
        }
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Username is already registered"}


def test_register_rejects_invalid_request_before_service_call(client, database_session ,monkeypatch) -> None:
    registration_service = Mock()

    monkeypatch.setattr(
        auth_routes,
        "register_user",
        registration_service
    )

    response = client.post(
        "/auth/register",
        json={
            "username": "alice",
            "password": "too-short"
        }
    )

    assert response.status_code == 422
    registration_service.assert_not_called()