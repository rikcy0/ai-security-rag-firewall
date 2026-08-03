from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from backend.app.db.database import SessionLocal
from backend.app.db.models import User
from backend.app.security.passwords import verify_password


TEST_PASSWORD = "integration-test-password"


@pytest.fixture
def unique_username() -> Iterator[str]:
    username = f"test-{uuid4().hex}" # each test is unique

    yield username

    with SessionLocal() as database_session:
        database_session.execute(delete(User).where(User.username == username))
        database_session.commit()


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