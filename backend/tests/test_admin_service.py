from unittest.mock import Mock

from sqlalchemy.orm import Session

from backend.app.db.models import User
from backend.app.services.admin import list_users


PASSWORD_HASH = "$argon2id$test-password-hash"


def test_list_users_returns_database_users() -> None:
    database_session = Mock(spec=Session)

    expected_users = [
        User(
            username="admin",
            password_hash=PASSWORD_HASH,
            role="admin",
            is_active=True
        ),
        User(
            username="alice",
            password_hash=PASSWORD_HASH,
            role="user",
            is_active=True
        )
    ]

    scalar_result = Mock()
    scalar_result.all.return_value = expected_users
    database_session.scalars.return_value = scalar_result

    result = list_users(database_session)

    assert result == expected_users
    database_session.scalars.assert_called_once()
    scalar_result.all.assert_called_once()