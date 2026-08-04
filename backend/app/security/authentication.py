from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.security.tokens import AccessTokenError, decode_access_token
from backend.app.services.auth import get_user_by_id


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False
)


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}
    )


# Token is returned as a string or None by oauth2 to utilize own authentication_error
def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    database_session: Annotated[Session, Depends(get_db)]) -> User:
    if token is None:
        raise authentication_error()
    try:
        user_id = decode_access_token(token)
    except AccessTokenError as exc:
        raise authentication_error() from exc

    user = get_user_by_id(database_session, user_id)

    if user is None or not user.is_active:
        raise authentication_error()

    return user