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

    # Rate limiting ("<count>/<window>", window: second|minute|hour|day). Redis-backed
    # (`rate_limit_redis_url`, default = the Celery broker); "memory" is for tests/dev only.
    rate_limit_backend: Literal["redis", "memory"] = "redis"
    rate_limit_redis_url: str | None = None
    rate_limit_login_ip: str = "30/minute"
    rate_limit_login_email: str = "8/15minute"  # brute force on one account, from any IP
    rate_limit_refresh: str = "30/minute"
    rate_limit_accept_invitation: str = "10/minute"
    rate_limit_generate: str = "10/hour"  # per user: POST /summaries/generate
    rate_limit_after_session: str = "30/hour"  # per user: POST /after-session-notes
    # Rolling 24h budget per user across all LLM calls (`llm_usage`); 0 disables a cap.
    llm_daily_request_limit: int = Field(default=200, ge=0)
    llm_daily_cost_limit_usd: float = Field(default=2.0, ge=0)

    # Observability. Tracing is off without a token; content is never sent either way.
    logfire_token: SecretStr | None = None
    # /metrics (Prometheus) is served only with this bearer token; without it the route is 404.
    metrics_token: SecretStr | None = None

    # Stale `running` job reaper (the worker died mid-job). Keep well above the LLM timeout.
    job_stale_after_seconds: int = Field(default=900, ge=60)
    job_reaper_interval_seconds: int = Field(default=60, ge=5)

    # Database pool.
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout_seconds: float = Field(default=30, gt=0)
    db_pool_recycle_seconds: int = Field(default=1800, ge=-1)

    @field_validator(
        "rate_limit_login_ip",
        "rate_limit_login_email",
        "rate_limit_refresh",
        "rate_limit_accept_invitation",
        "rate_limit_generate",
        "rate_limit_after_session",
    )
    @classmethod
    def _valid_rate_limit(cls, value: str) -> str:
        from app.core.ratelimit import parse_limit  # noqa: PLC0415  (avoids an import cycle)

        parse_limit(value)
        return value

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
