from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError

from backend.app.config import get_settings

ALGORITHM = "HS256"


class AccessTokenError(Exception):
    """ Raises an error when the access token is not safely validated"""


def create_access_token(subject: UUID) -> str:
    settings = get_settings()
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expire_minutes)

    payload = {
        "sub": str(subject),
        "iat": issued_at,
        "exp": expires_at
    }

    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM
    )


def decode_access_token(token: str) -> UUID:
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=ALGORITHM,
            options={"require": ["sub", "iat", "exp"]}
        )
        return UUID(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise AccessTokenError("Invalid or expired access token") from exc