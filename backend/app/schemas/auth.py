from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


USERNAME_PATTERN = r"^[a-z0-9_-]+$"


class UsernameInput(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=USERNAME_PATTERN
    )

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

class UserRegistration(UsernameInput):
    # Enforce new-acccount password policy
    password: SecretStr = Field(
        min_length=15,
        max_length=128
    )

class UserLogin(UsernameInput):
    # Accepts eisting passwords even if they predate the current registration policy
    password: SecretStr = Field(
        min_length=1, 
        max_length=128
    )


class UserResponse(BaseModel):
    # Defines the safe user information returned to clients
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    # Login response
    access_token: str = Field(min_length=1)
    token_type: Literal["bearer"] = "bearer"