from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import User
from backend.app.schemas.auth import UserRegistration
from backend.app.security.passwords import hash_password


class UsernameAlreadyExistsError(Exception):
    """Raised when user registers with an existing username"""


def get_user_by_username(database_session: Session, username: str) -> User | None:
    statement = select(User).where(
        User.username == username
    ) # this constructs SQL: SELECT * FROM users WHERE username = :username_1;
    return database_session.scalar(statement)

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
