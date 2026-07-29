import pytest
from pydantic import ValidationError
from backend.app.config import Settings

# monkeypatch from pytest allows tetsts to temporarily change parts of the program's env
# Not a dummy model, parts of a test are replaced or modified, then restored

def test_database_url_is_loaded_from_environment(monkeypatch) -> None:
    database_url = (
        "postgresql+psycopg2://test_user:test_password@localhost:5432/test_database"
    )
    monkeypatch.setenv("RAG_FIREWALL_DATABASE_URL", database_url)
    settings = Settings(_env_file=None)

    assert settings.database_url.get_secret_value() == database_url


def test_database_url_is_hidden_in_settings_representation(monkeypatch) -> None:
    database_url = (
        "postgresql+psycopg2://test_user:secret_password@localhost:5432/test_database"
    )
    monkeypatch.setenv("RAG_FIREWALL_DATABASE_URL", database_url)
    settings = Settings(_env_file=None)

    assert database_url not in repr(settings)
    assert "secret_password" not in repr(settings)


def test_database_url_is_required(monkeypatch) -> None:
    monkeypatch.delenv("RAG_FIREWALL_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_unprefixed_environment_variables_are_ignored(monkeypatch) -> None:
    database_url = (
        "postgresql+psycopg2://test_user:test_password@localhost:5432/test_database"
    )
    monkeypatch.setenv("RAG_FIREWALL_DATABASE_URL", database_url)
    monkeypatch.setenv("DEBUG", "release")
    settings = Settings(_env_file=None)

    assert settings.debug is False