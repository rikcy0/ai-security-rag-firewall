from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import get_settings

class Base(DeclarativeBase):
    """ Foundation for future ORM classes """
    pass

settings = get_settings()

engine = create_engine(
    settings.database_url.get_secret_value(),
    pool_pre_ping=True  # avoid stale/broken connections in the pool
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False
)

def get_db() -> Generator[Session, None, None]:
    """ Provide one DB session, close it afterward. """

    database_session = SessionLocal()
    try: 
        yield database_session
    finally: 
        database_session.close()