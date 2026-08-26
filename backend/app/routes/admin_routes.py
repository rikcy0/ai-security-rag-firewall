from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.schemas.auth import UserResponse
from backend.app.security.access_control import require_admin
from backend.app.services.admin import list_users
from backend.app.schemas.security_events import SecurityEventResponse
from backend.app.services.security_events import (
    DEFAULT_SECURITY_EVENT_LIMIT,
    MAX_SECURITY_EVENT_LIMIT,
    list_security_events,
)


router = APIRouter(
    prefix="/admin",
    tags=["administration"]
)


@router.get(
    "/users",
    response_model=list[UserResponse]
)
def read_users( # require_admin is resolved by FastAPI before read_users() executes
    current_admin: Annotated[User, Depends(require_admin)],
    database_session: Annotated[Session, Depends(get_db)]
) -> list[UserResponse]:
    users = list_users(database_session)
    return [UserResponse.model_validate(user) for user in users]


@router.get(
    "/security-events",
    response_model=list[SecurityEventResponse]
)
def read_security_events(
    current_admin: Annotated[User, Depends(require_admin)],
    database_session: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int, Query(ge=1, le=MAX_SECURITY_EVENT_LIMIT)
    ] = DEFAULT_SECURITY_EVENT_LIMIT
) -> list[SecurityEventResponse]:
    events = list_security_events(database_session, limit=limit)
    return [SecurityEventResponse.model_validate(event) for event in events]