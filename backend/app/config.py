from functools import lru_cache
from pathlib import Path
from typing import Literal   #limits a value to a specific set of allowed strings

# pydantic: settings class that controls behavior and hides values
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    """
    Central source of application configuration.

    Keeping settings in one validated object prevents different parts of the application
    from reading env variable in inconsistent ways. 
    Values with safe defaults can be used immediately during development.
    Sensitive or deployment-specific values are to be supplied externally.

    Application code should normally use get_settings()
    """

    app_name: str = "AI Security RAG Firewall"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    database_url: SecretStr
    secret_key: SecretStr = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=60, ge=1, le=1440)

    max_upload_size_bytes: int = Field(
        default=1_048_576,
        ge=1,
        le=10_485_760
    )
    chunk_size_characters: int = Field(
        default=1_000,
        ge=100,
        le=10_000
    )
    chunk_overlap_characters: int = Field(
        default=200,
        ge=0,
        le=2_000
    )

    openai_api_key: SecretStr | None = None

    embedding_model: str = Field(
        default="text-embedding-3-small",
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    )

    generation_model: str = Field(
        default="gpt-5.6-luna",
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    )

    rag_answer_top_k: int = Field(
        default=5,
        ge=1,
        le=20
    )
    rag_max_context_characters: int = Field(
        default=20_000,
        ge=1,
        le=100_000
    )
    rag_max_output_tokens: int = Field(
        default=800,
        ge=16,
        le=4_000
    )

    openai_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=300
    )
    openai_max_retries: int = Field(
        default=1,
        ge=0,
        le=5
    )

    prompt_injection_block_threshold: int = Field(
        default=50,
        ge=1,
        le=100
    )

    model_config = SettingsConfigDict(
        env_prefix="RAG_FIREWALL_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore", #config will not fail upon unknown values in .env
    )

    @model_validator(mode="after")
    def validate_chunk_configuration(self) -> "Settings":
        if self.chunk_overlap_characters >= self.chunk_size_characters:
            raise ValueError("Chunk overlap must be smaller than chunk size")
        if self.rag_max_context_characters < self.chunk_size_characters:
            raise ValueError("RAG context limit must be at least as large as chunk size")

        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()