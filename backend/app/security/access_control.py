from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from backend.app.db.models import User, UserRole
from backend.app.security.authentication import get_current_user
from backend.app.services.security_events import record_authorization_denial


"""
Dependency factory:
- This function does not directly check a user. 
- It creates and returns another function that checks for one particular role
- Depends(get_current_user): authorization happens after authentication
    Request -> Extract Bearer token -> Validate JWT -> Load active user from DB -> check user role

In other words: the last line in this file calls the require_role() once when this module is imported
"""


def require_role(required_role: UserRole) -> Callable[[User], User]:
    # FastAPI must resolve get_current_user first (Depends)
    def role_checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role != required_role.value:
            record_authorization_denial(
                actor_user_id=current_user.id,
                actor_username=current_user.username,
                required_role=required_role,
                actual_role=current_user.role
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return role_checker

# conceptually creates: if user is not admin, HTTP error on request
require_admin = require_role(UserRole.ADMIN)