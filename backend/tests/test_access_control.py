from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.app.db.models import User, UserRole
from backend.app.security import access_control


PASSWORD_HASH = "$argon2id$test-password-hash"


def make_user(role: UserRole) -> User:
    user = User(
        username="alice",
        password_hash=PASSWORD_HASH,
        role=role.value,
        is_active=True
    )
    user.id = uuid4()

    return user


def test_require_admin_returns_admin_user() -> None:
    admin_user = make_user(UserRole.ADMIN)
    result = access_control.require_admin(admin_user)

    assert result is admin_user


def test_require_admin_rejects_ordinary_user() -> None:
    ordinary_user = make_user(UserRole.USER)

    with pytest.raises(HTTPException) as exc_info:
        access_control.require_admin(ordinary_user)

    exception = exc_info.value

    assert exception.status_code == 403
    assert exception.detail == "Insufficient permissions"
    assert exception.headers is None


# proves require_role() is reusable rather than hardcoded to admins
def test_require_role_creates_role_specific_checker() -> None:
    ordinary_user = make_user(UserRole.USER)
    require_user = access_control.require_role(UserRole.USER)

    result = require_user(ordinary_user)

    assert result is ordinary_user