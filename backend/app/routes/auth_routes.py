from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.schemas.auth import UserRegistration, UserResponse
from backend.app.services.auth import UsernameAlreadyExistsError, register_user


router = APIRouter(
    prefix="/auth",
    tags=["authentication"]
)

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register(registration: UserRegistration, database_session: Annotated[Session, Depends(get_db)]) -> UserResponse:
    try:
        user = register_user(database_session, registration)
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already registered"
        ) from exc

    return UserResponse.model_validate(user)
