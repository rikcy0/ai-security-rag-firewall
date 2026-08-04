from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import User
from backend.app.schemas.auth import UserLogin, UserRegistration
from backend.app.security.passwords import hash_password, verify_password


class UsernameAlreadyExistsError(Exception):
    """Raised when user registers with an existing username"""


class InvalidCredentialsError(Exception):
    """Raised when login credentials are invalid"""


# Performs password verification even when the username is unknown,
# to reduce username-enumeration signals from response timing (a bonus security policy)
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-user-password")


def get_user_by_username(database_session: Session, username: str) -> User | None:
    statement = select(User).where(
        User.username == username
    ) # this constructs SQL: SELECT * FROM users WHERE username = :username_1;
    return database_session.scalar(statement)


def get_user_by_id(database_session: Session, user_id: UUID) -> User | None:
    return database_session.get(User, user_id)


def register_user(database_session: Session, registration: UserRegistration) -> User:
    existing_user = get_user_by_username(database_session, registration.username)

    if existing_user is not None:
        raise UsernameAlreadyExistsError("Username is already registered")

    plaintext_password = registration.password.get_secret_value()
    password_hash = hash_password(plaintext_password)

    user = User(username=registration.username, password_hash=password_hash)
    database_session.add(user)

    # Catch simultaneous requests in a race condition
    try:
        database_session.commit()
    except IntegrityError as exc:
        database_session.rollback()
        raise UsernameAlreadyExistsError("Username is already registered") from exc

    database_session.refresh(user)

    return user


def authenticate_user(database_session: Session, login: UserLogin) -> User:
    user = get_user_by_username(database_session, login.username)
    plaintext_password = login.password.get_secret_value()

    # user exists: verify w/user's real hash
    # user missing: verify against dummy hash
    # more costly (Argon2)
    if user is None:
        stored_hash = _DUMMY_PASSWORD_HASH
    else:
        stored_hash = user.password_hash

    password_is_valid = verify_password(plaintext_password, stored_hash)

    if user is None or not password_is_valid or not user.is_active:
        raise InvalidCredentialsError("Incorrect username or password")

    return user