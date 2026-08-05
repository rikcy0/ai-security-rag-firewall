from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.schemas.auth import UserResponse
from backend.app.security.access_control import require_admin
from backend.app.services.admin import list_users


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
    database_session: Annotated[Session, Depends(get_db)]) -> list[UserResponse]:
    users = list_users(database_session)
    return [UserResponse.model_validate(user) for user in users]