from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import User


def list_users(database_session: Session) -> list[User]:
    statement = select(User).order_by(User.username)
    return list(database_session.scalars(statement).all())