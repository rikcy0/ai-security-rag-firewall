from functools import lru_cache
from pathlib import Path
from typing import Literal   #limits a value to a specific set of allowed strings

# pydantic: settings class that controls behavior and hides values
from pydantic import Field, SecretStr
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

    model_config = SettingsConfigDict(
        env_prefix="RAG_FIREWALL_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore", #config will not fail upon unknown values in .env
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()