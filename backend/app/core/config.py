from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLACEHOLDER_MARKERS = ("replace-with", "change-me", "changeme", "your-secret", "example")


def normalize_database_url(url: str) -> str:
    """Forces the asyncpg driver on plain `postgres://` / `postgresql://` URLs and maps the
    libpq `sslmode` query parameter (used by Supabase and most providers) to asyncpg's `ssl`,
    which is the only spelling asyncpg accepts."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix) :]
            break
    base, sep, query = url.partition("?")
    if not sep:
        return url
    params = parse_qsl(query, keep_blank_values=True)
    if any(key == "sslmode" for key, _ in params):
        has_ssl = any(key == "ssl" for key, _ in params)
        params = [
            ("ssl", value) if key == "sslmode" else (key, value)
            for key, value in params
            if not (key == "sslmode" and has_ssl)
        ]
        return f"{base}?{urlencode(params)}"
    return url


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
    # Absolute session length, counted from login: refreshing never extends it.
    session_max_days: int = Field(default=30, ge=1)
    invitation_hours: int = Field(default=72, ge=1)
    seed_password: SecretStr | None = None  # demo seed only
    # Explicit opt-in to run the (synthetic) demo seed with APP_ENV=production.
    seed_demo: bool = False
    # One-click demo sign-in (POST /auth/demo-login) for the seeded demo-clinic accounts only.
    # Off by default; the public demo deployment turns it on explicitly.
    demo_login_enabled: bool = False

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
    rate_limit_logout: str = "30/minute"  # fail-open: logout must still revoke when Redis is down
    rate_limit_accept_invitation: str = "10/minute"
    rate_limit_generate: str = "10/hour"  # per user: POST /summaries/generate
    rate_limit_after_session: str = "30/hour"  # per user: POST /after-session-notes
    rate_limit_export: str = "5/hour"  # per user: GET /account/export
    rate_limit_account_delete: str = "5/hour"  # per user: DELETE /account (password guesses)
    rate_limit_topics: str = "60/hour"  # per user: PUT /summaries/{id}/topics
    rate_limit_demo_login: str = "10/minute"  # per IP: POST /auth/demo-login
    # The client's calendar day for in-app reminders ("tomorrow's appointment").
    reminder_timezone: str = "Europe/Istanbul"
    # Rolling 24h budget per user across all LLM calls (`llm_usage`); 0 disables a cap.
    llm_daily_request_limit: int = Field(default=200, ge=0)
    llm_daily_cost_limit_usd: float = Field(default=2.0, ge=0)

    # Reverse proxies in front of the app (Render: 1). 0 = ignore X-Forwarded-For. With N > 0
    # the client IP is the Nth entry from the right of X-Forwarded-For (appended by our own
    # proxies, so not spoofable); anything further left is client-controlled and ignored.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=10)

    # Observability. Tracing is off without a token; content is never sent either way.
    logfire_token: SecretStr | None = None
    # /metrics (Prometheus) is served only with this bearer token; without it the route is 404.
    metrics_token: SecretStr | None = None

    # Stale `running` job reaper (the worker died mid-job). Keep well above the LLM timeout.
    job_stale_after_seconds: int = Field(default=900, ge=60)
    job_reaper_interval_seconds: int = Field(default=60, ge=5)
    refresh_purge_interval_seconds: int = Field(default=3600, ge=60)

    # CORS for a separately served frontend: comma-separated origins. Empty = CORS off.
    # A wildcard is rejected.
    cors_origins: str = ""

    # Database pool.
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout_seconds: float = Field(default=30, gt=0)
    db_pool_recycle_seconds: int = Field(default=1800, ge=-1)

    @field_validator(
        "rate_limit_login_ip",
        "rate_limit_login_email",
        "rate_limit_refresh",
        "rate_limit_logout",
        "rate_limit_accept_invitation",
        "rate_limit_generate",
        "rate_limit_after_session",
        "rate_limit_export",
        "rate_limit_account_delete",
        "rate_limit_topics",
        "rate_limit_demo_login",
    )
    @classmethod
    def _valid_rate_limit(cls, value: str) -> str:
        from app.core.ratelimit import parse_limit  # noqa: PLC0415  (avoids an import cycle)

        parse_limit(value)
        return value

    @field_validator("database_url")
    @classmethod
    def _asyncpg_driver(cls, value: str) -> str:
        # Managed Postgres (Supabase, Render) hands out `postgresql://` / `postgres://` URLs.
        return normalize_database_url(value)

    @field_validator("anthropic_api_key", "logfire_token", "metrics_token", mode="before")
    @classmethod
    def _blank_optional_secret_is_unset(cls, value: object) -> object:
        # A blank env var (e.g. an empty dashboard field) must mean "not configured": an empty
        # METRICS_TOKEN would otherwise expose /metrics behind an empty bearer token.
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, SecretStr) and not value.get_secret_value().strip():
            return None
        return value

    @field_validator("jwt_secret")
    @classmethod
    def _reject_placeholder_secret(cls, value: SecretStr) -> SecretStr:
        lowered = value.get_secret_value().lower()
        if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            raise ValueError("JWT_SECRET is a placeholder; generate a random value")
        return value

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origin(cls, value: str) -> str:
        if "*" in value:
            raise ValueError("CORS_ORIGINS must list explicit origins, not a wildcard")
        return value

    @model_validator(mode="after")
    def _production_needs_shared_rate_limiter(self) -> "Settings":
        if self.app_env == "production" and self.rate_limit_backend == "memory":
            raise ValueError("RATE_LIMIT_BACKEND=memory is not allowed when APP_ENV=production")
        if self.app_env == "production" and "trusted_proxy_hops" not in self.model_fields_set:
            raise ValueError(
                "TRUSTED_PROXY_HOPS must be set explicitly when APP_ENV=production "
                "(Render: 1; 0 only if there is no proxy): the default would put all clients "
                "in one rate-limit bucket"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
