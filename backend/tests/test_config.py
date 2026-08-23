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


# Prompt-injection detector configuration

def test_prompt_injection_block_threshold_defaults_to_50(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    settings = Settings(_env_file=None)

    assert settings.prompt_injection_block_threshold == 50


@pytest.mark.parametrize(
    "invalid_threshold",
    ["0", "101"],
)
def test_prompt_injection_block_threshold_must_be_between_1_and_100(monkeypatch, invalid_threshold: str) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_PROMPT_INJECTION_BLOCK_THRESHOLD",
        invalid_threshold
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# Embedding configuration

def test_openai_api_key_is_optional(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.delenv(
        "RAG_FIREWALL_OPENAI_API_KEY",
        raising=False
    )

    settings = Settings(_env_file=None)
    assert settings.openai_api_key is None


def test_openai_api_key_is_hidden_in_settings_representation(monkeypatch) -> None:
    database_url = ("postgresql+psycopg2://user:password@localhost/test_database")
    api_key = "test-openai-api-key"

    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        database_url
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_OPENAI_API_KEY",
        api_key
    )

    settings = Settings(_env_file=None)

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == api_key
    assert api_key not in repr(settings)


def test_embedding_model_defaults_to_text_embedding_3_small(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.delenv(
        "RAG_FIREWALL_EMBEDDING_MODEL",
        raising=False
    )

    settings = Settings(_env_file=None)
    assert settings.embedding_model == "text-embedding-3-small"


@pytest.mark.parametrize(
    "invalid_model",
    [
        "",
        " ",
        "model name with spaces",
        "x" * 101,
    ],
)
def test_embedding_model_rejects_invalid_values(monkeypatch, invalid_model: str) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_EMBEDDING_MODEL",
        invalid_model
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# Guarded RAG answer configuration

def test_rag_answer_settings_have_bounded_defaults(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )

    settings = Settings(_env_file=None)

    assert settings.generation_model == "gpt-5.6-luna"
    assert settings.rag_answer_top_k == 5
    assert settings.rag_max_context_characters == 20_000
    assert settings.rag_max_output_tokens == 800
    assert settings.openai_timeout_seconds == 30.0
    assert settings.openai_max_retries == 1


@pytest.mark.parametrize(
    "invalid_model",
    [
        "",
        " ",
        "model name with spaces",
        "x" * 101,
    ],
)
def test_generation_model_rejects_invalid_values(monkeypatch, invalid_model: str) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_GENERATION_MODEL",
        invalid_model
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("environment_variable", "invalid_value"),
    [
        ("RAG_FIREWALL_RAG_ANSWER_TOP_K", "0"),
        ("RAG_FIREWALL_RAG_ANSWER_TOP_K", "21"),
        ("RAG_FIREWALL_RAG_MAX_CONTEXT_CHARACTERS", "0"),
        ("RAG_FIREWALL_RAG_MAX_CONTEXT_CHARACTERS", "100001"),
        ("RAG_FIREWALL_RAG_MAX_OUTPUT_TOKENS", "0"),
        ("RAG_FIREWALL_RAG_MAX_OUTPUT_TOKENS", "4001"),
        ("RAG_FIREWALL_OPENAI_TIMEOUT_SECONDS", "0"),
        ("RAG_FIREWALL_OPENAI_TIMEOUT_SECONDS", "301"),
        ("RAG_FIREWALL_OPENAI_MAX_RETRIES", "-1"),
        ("RAG_FIREWALL_OPENAI_MAX_RETRIES", "6"),
    ],
)
def test_rag_answer_settings_reject_out_of_range_values(
    monkeypatch,
    environment_variable: str,
    invalid_value: str
) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv(environment_variable, invalid_value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_rag_context_budget_must_hold_one_configured_chunk(monkeypatch) -> None:
    monkeypatch.setenv(
        "RAG_FIREWALL_DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost/test_database"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_CHUNK_SIZE_CHARACTERS",
        "1000"
    )
    monkeypatch.setenv(
        "RAG_FIREWALL_RAG_MAX_CONTEXT_CHARACTERS",
        "999"
    )

    with pytest.raises(
        ValidationError,
        match="RAG context limit must be at least as large as chunk size"
    ):
        Settings(_env_file=None)