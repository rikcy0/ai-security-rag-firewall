import pytest
from sqlalchemy import text

from backend.app.db import database


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

#unit test
def test_get_db_closes_session(monkeypatch) -> None:
    fake_session = FakeSession()

    monkeypatch.setattr(
        database,
        "SessionLocal",
        lambda: fake_session,
    )
    session_generator = database.get_db()
    yielded_session = next(session_generator)

    assert yielded_session is fake_session # check if fake session is yielded and open
    assert fake_session.closed is False

    with pytest.raises(StopIteration): # signals that a generator has finished
        next(session_generator)

    assert fake_session.closed is True

# integration test
@pytest.mark.integration
def test_database_accepts_queries() -> None:
    with database.engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar_one()

    assert result == 1