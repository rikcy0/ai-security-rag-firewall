from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from backend.app.db.database import SessionLocal
from backend.app.db.models import User, UserRole


TEST_PASSWORD = "integration-test-password"


@pytest.fixture
def rbac_usernames() -> Iterator[tuple[str, str]]:
    suffix = uuid4().hex
    admin_username = f"admin-{suffix}"
    ordinary_username = f"user-{suffix}"

    yield admin_username, ordinary_username

    with SessionLocal() as database_session:
        database_session.execute(
            delete(User).where(
                User.username.in_(
                    [
                        admin_username,
                        ordinary_username,
                    ]
                )
            )
        )
        database_session.commit()


# Helper functions
def register_user(client: TestClient, username: str) -> None:
    response = client.post(
        "/auth/register",
        json={
            "username": username,
            "password": TEST_PASSWORD,
        }
    )
    assert response.status_code == 201

def login_user(client: TestClient, username: str) -> str:
    response = client.post(
        "/auth/login",
        data={
            "username": username,
            "password": TEST_PASSWORD,
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]

def set_user_role(username: str, role: UserRole) -> None:
    with SessionLocal() as database_session:
        user = database_session.scalar(
            select(User).where(
                User.username == username
            )
        )
        assert user is not None
        user.role = role.value
        database_session.commit()


@pytest.mark.integration
def test_ordinary_user_cannot_access_admin_users(client: TestClient, rbac_usernames: tuple[str, str]) -> None:
    _, ordinary_username = rbac_usernames

    register_user(client, ordinary_username)
    access_token = login_user(client, ordinary_username)

    response = client.get(
        "/admin/users",
        headers={
            "Authorization": f"Bearer {access_token}",
        }
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}
    assert "www-authenticate" not in response.headers


@pytest.mark.integration
def test_admin_can_list_safe_database_users(client: TestClient, rbac_usernames: tuple[str, str]) -> None:
    admin_username, ordinary_username = (rbac_usernames)
    register_user(client, admin_username)
    register_user(client, ordinary_username)

    set_user_role(admin_username, UserRole.ADMIN)
    access_token = login_user(client, admin_username)

    response = client.get(
        "/admin/users",
        headers={
            "Authorization": f"Bearer {access_token}",
        }
    )

    assert response.status_code == 200

    response_data = response.json()

    users_by_username = {
        user["username"]: user
        for user in response_data
    }

    assert users_by_username[admin_username]["role"] == "admin"
    assert users_by_username[ordinary_username]["role"] == "user"

    for user_data in response_data:
        assert set(user_data) == {
            "id",
            "username",
            "role",
            "is_active",
            "created_at",
        }
        assert "password" not in user_data
        assert "password_hash" not in user_data

    returned_usernames = [user["username"] for user in response_data]
    assert returned_usernames == sorted(returned_usernames)


@pytest.mark.integration
def test_admin_token_loses_access_after_demotion(client: TestClient, rbac_usernames: tuple[str, str]) -> None:
    admin_username, _ = rbac_usernames

    register_user(client, admin_username,)
    set_user_role(admin_username, UserRole.ADMIN)

    access_token = login_user(client, admin_username)
    set_user_role(admin_username, UserRole.USER)

    response = client.get(
        "/admin/users",
        headers={
            "Authorization": f"Bearer {access_token}",
        }
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}