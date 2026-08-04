from unittest.mock import Mock

import pytest
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import User
from backend.app.schemas.auth import UserLogin, UserRegistration
from backend.app.services import auth as auth_service
from backend.app.services.auth import InvalidCredentialsError, UsernameAlreadyExistsError


PLAINTEXT_PASSWORD = "a-secure-password"
PASSWORD_HASH = "$argon2id$test-password-hash"
DUMMY_PASSWORD_HASH = "$argon2id$dummy-test-hash"


# HELPER FUNCTIONS
def make_registration() -> UserRegistration:
    return UserRegistration(
        username="Alice",
        password=PLAINTEXT_PASSWORD
    )

def make_login(password: str = PLAINTEXT_PASSWORD) -> UserLogin:
    return UserLogin(
        username="  Alice  ",
        password=password,
    )


def test_get_user_by_username_returns_matching_user() -> None:
    database_session = Mock(spec=Session)
    expected_user = User(
        username="alice",
        password_hash=PASSWORD_HASH
    )
    database_session.scalar.return_value = expected_user

    result = auth_service.get_user_by_username(
        database_session,
        "alice"
    )

    assert result is expected_user
    database_session.scalar.assert_called_once()


def test_register_user_hashes_password_and_commits(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    database_session.scalar.return_value = None

    password_hasher = Mock(return_value=PASSWORD_HASH)
    monkeypatch.setattr(
        auth_service,
        "hash_password",
        password_hasher
    )

    registration = make_registration()
    user = auth_service.register_user(
        database_session,
        registration
    )

    password_hasher.assert_called_once_with(PLAINTEXT_PASSWORD)

    assert user.username == "alice"
    assert user.password_hash == PASSWORD_HASH
    assert user.password_hash != PLAINTEXT_PASSWORD
    assert not hasattr(user, "password")

    database_session.add.assert_called_once_with(user)
    database_session.commit.assert_called_once()
    database_session.refresh.assert_called_once_with(user)
    database_session.rollback.assert_not_called()


def test_register_user_rejects_existing_username(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    database_session.scalar.return_value = User(
        username="alice",
        password_hash=PASSWORD_HASH
    )

    password_hasher = Mock(return_value=PASSWORD_HASH)
    monkeypatch.setattr(
        auth_service,
        "hash_password",
        password_hasher
    )

    with pytest.raises(
        UsernameAlreadyExistsError,
        match="Username is already registered",
    ):
        auth_service.register_user(
            database_session,
            make_registration()
        )

    password_hasher.assert_not_called()
    database_session.add.assert_not_called()
    database_session.commit.assert_not_called()


def test_register_user_rolls_back_database_uniqueness_conflict(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    database_session.scalar.return_value = None
    database_session.commit.side_effect = IntegrityError(
        statement="INSERT INTO users",
        params={},
        orig=Exception("duplicate username")
    )

    monkeypatch.setattr(
        auth_service,
        "hash_password",
        Mock(return_value=PASSWORD_HASH)
    )

    with pytest.raises(UsernameAlreadyExistsError):
        auth_service.register_user(
            database_session,
            make_registration()
        )

    database_session.rollback.assert_called_once()
    database_session.refresh.assert_not_called()


def test_authenticate_user_returns_user_for_valid_credentials(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    expected_user = User(
        username="alice",
        password_hash=PASSWORD_HASH,
        is_active=True
    )
    database_session.scalar.return_value = expected_user

    password_verifier = Mock(return_value=True)
    monkeypatch.setattr(
        auth_service,
        "verify_password",
        password_verifier
    )

    result = auth_service.authenticate_user(
        database_session,
        make_login()
    )

    assert result is expected_user

    password_verifier.assert_called_once_with(
        PLAINTEXT_PASSWORD,
        PASSWORD_HASH
    )
    database_session.commit.assert_not_called()


def test_authenticate_user_rejects_incorrect_password(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    database_session.scalar.return_value = User(
        username="alice",
        password_hash=PASSWORD_HASH,
        is_active=True
    )

    monkeypatch.setattr(
        auth_service,
        "verify_password",
        Mock(return_value=False)
    )

    with pytest.raises(
        InvalidCredentialsError,
        match="Incorrect username or password"
    ):
        auth_service.authenticate_user(
            database_session,
            make_login(password="wrong")
        )


def test_authenticate_user_uses_dummy_hash_for_unknown_username(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    database_session.scalar.return_value = None

    password_verifier = Mock(return_value=True)

    monkeypatch.setattr(
        auth_service,
        "_DUMMY_PASSWORD_HASH",
        DUMMY_PASSWORD_HASH
    )
    monkeypatch.setattr(
        auth_service,
        "verify_password",
        password_verifier
    )

    with pytest.raises(
        InvalidCredentialsError,
        match="Incorrect username or password"
    ):
        auth_service.authenticate_user(
            database_session,
            make_login()
        )

    password_verifier.assert_called_once_with(
        PLAINTEXT_PASSWORD,
        DUMMY_PASSWORD_HASH
    )


def test_authenticate_user_rejects_inactive_user(monkeypatch) -> None:
    database_session = Mock(spec=Session)
    database_session.scalar.return_value = User(
        username="alice",
        password_hash=PASSWORD_HASH,
        is_active=False
    )

    password_verifier = Mock(return_value=True)
    monkeypatch.setattr(
        auth_service,
        "verify_password",
        password_verifier
    )

    with pytest.raises(
        InvalidCredentialsError,
        match="Incorrect username or password"
    ):
        auth_service.authenticate_user(
            database_session,
            make_login()
        )

    password_verifier.assert_called_once_with(
        PLAINTEXT_PASSWORD,
        PASSWORD_HASH
    )


def test_get_user_by_id_returns_matching_user() -> None:
    database_session = Mock(spec=Session)
    user_id = uuid4()

    expected_user = User(
        username="alice",
        password_hash=PASSWORD_HASH,
        is_active=True
    )
    expected_user.id = user_id
    database_session.get.return_value = expected_user

    result = auth_service.get_user_by_id(database_session, user_id)

    assert result is expected_user
    database_session.get.assert_called_once_with(User, user_id)