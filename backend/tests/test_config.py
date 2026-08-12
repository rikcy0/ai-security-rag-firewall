import pytest
from pydantic import ValidationError

from backend.app.config import Settings

# monkeypatch temporarily changes environment variables during a test.
# Pytest restores the original environment after the test finishes.

TEST_SECRET_KEY = "x" * 32


@pytest.fixture(autouse=True)
def provide_required_secret_key(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_SECRET_KEY",
        TEST_SECRET_KEY
    )


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

# JWT configuration tests

def test_secret_key_is_hidden_in_settings_representation(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    settings = Settings(_env_file=None)

    assert TEST_SECRET_KEY not in repr(settings)
    assert settings.access_token_expire_minutes == 60


def test_secret_key_is_required(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.delenv("RAG_FIREWALL_SECRET_KEY")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_secret_key_rejects_short_values(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv("RAG_FIREWALL_SECRET_KEY", "too-short")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_access_token_expiration_must_be_positive(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_ACCESS_TOKEN_EXPIRE_MINUTES",
        "0"
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# doc chunking limits
def test_document_processing_defaults(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )

    settings = Settings(_env_file=None)

    assert settings.max_upload_size_bytes == 1_048_576
    assert settings.chunk_size_characters == 1_000
    assert settings.chunk_overlap_characters == 200


def test_upload_size_must_be_positive(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_MAX_UPLOAD_SIZE_BYTES",
        "0"
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_upload_size_rejects_excessive_limit(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_MAX_UPLOAD_SIZE_BYTES",
        str(10_485_761)
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_chunk_overlap_must_be_smaller_than_chunk_size(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_CHUNK_SIZE_CHARACTERS",
        "500"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_CHUNK_OVERLAP_CHARACTERS",
        "500"
    )

    with pytest.raises(ValidationError, match="Chunk overlap must be smaller than chunk size"):
        Settings(_env_file=None)