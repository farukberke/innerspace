"""Per-user LLM budget over a rolling 24 hours, from `llm_usage` (counts failed calls too)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import LlmUsage, User
from app.services.errors import RateLimitedError

WINDOW = timedelta(hours=24)


async def check_daily_budget(session: AsyncSession, settings: Settings, user: User) -> None:
    """Raises RateLimitedError when the user's last-24h LLM requests or cost reach the cap."""
    since = datetime.now(UTC) - WINDOW
    requests, cost, oldest = (
        await session.execute(
            select(
                func.coalesce(func.sum(LlmUsage.requests), 0),
                func.coalesce(func.sum(LlmUsage.cost_usd), 0),
                func.min(LlmUsage.created_at),
            ).where(LlmUsage.user_id == user.id, LlmUsage.created_at >= since)
        )
    ).one()
    over_requests = 0 < settings.llm_daily_request_limit <= requests
    over_cost = 0 < settings.llm_daily_cost_limit_usd <= float(cost)
    if over_requests or over_cost:
        retry_after = int((oldest + WINDOW - datetime.now(UTC)).total_seconds()) if oldest else 3600
        raise RateLimitedError(retry_after)
