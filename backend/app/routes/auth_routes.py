from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.schemas.auth import TokenResponse, UserLogin, UserRegistration, UserResponse
from backend.app.services.auth import InvalidCredentialsError, UsernameAlreadyExistsError, authenticate_user, register_user
from backend.app.security.tokens import create_access_token
from backend.app.security.authentication import get_current_user
from backend.app.db.models import User
from backend.app.services.security_events import record_failed_login


router = APIRouter(
    prefix="/auth",
    tags=["authentication"]
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register(
    registration: UserRegistration,
    database_session: Annotated[Session, Depends(get_db)]) -> UserResponse:
    try:
        user = register_user(database_session, registration)
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already registered"
        ) from exc

    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse
)
def login(
    credentials: Annotated[UserLogin, Form()],
    database_session: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    try:
        user = authenticate_user(database_session, credentials)
    except InvalidCredentialsError as exc:
        record_failed_login(
            actor_username=credentials.username
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"}
        ) from exc

    access_token = create_access_token(user.id)
    return TokenResponse(access_token=access_token)


@router.get(
    "/me",
    response_model=UserResponse
)
def read_current_user(current_user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return UserResponse.model_validate(current_user)