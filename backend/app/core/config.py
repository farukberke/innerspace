from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLACEHOLDER_MARKERS = ("replace-with", "change-me", "changeme", "your-secret", "example")


class Settings(BaseSettings):
    """Application configuration, read from environment variables and the repo-root `.env`."""

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_url: str = Field(min_length=1)

    # Auth. The signing algorithm is fixed in code (HS256), never read from tokens or env.
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = Field(default=15, ge=1)
    refresh_token_days: int = Field(default=7, ge=1)
    invitation_hours: int = Field(default=72, ge=1)
    seed_password: SecretStr | None = None  # demo seed only

    # AI. Without an API key the AI endpoints answer 503. The key only ever comes from the env.
    llm_model: str = "anthropic:claude-sonnet-5-5"  # "<provider>:<model>"; only anthropic for now
    anthropic_api_key: SecretStr | None = None
    llm_max_retries: int = Field(default=2, ge=0, le=5)  # guardrail / validation re-generations
    llm_timeout_seconds: float = Field(default=60, gt=0)
    # Estimated price in USD per million tokens, for cost tracking only.
    llm_input_usd_per_mtok: float = Field(default=3.0, ge=0)
    llm_output_usd_per_mtok: float = Field(default=15.0, ge=0)

    # Background jobs (Celery). Task payloads carry only a job id; results are never stored.
    celery_broker_url: str = "redis://localhost:6380/0"
    job_max_retries: int = Field(default=3, ge=0, le=10)  # transient failures only
    job_retry_backoff_seconds: int = Field(default=10, ge=1)  # doubles every retry

    @field_validator("jwt_secret")
    @classmethod
    def _reject_placeholder_secret(cls, value: SecretStr) -> SecretStr:
        lowered = value.get_secret_value().lower()
        if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            raise ValueError("JWT_SECRET is a placeholder; generate a random value")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
