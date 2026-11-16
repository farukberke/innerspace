"""Fixed-window rate limiting. Redis in production, in-memory for tests/dev.

Keys never contain raw e-mail addresses (hashed). If Redis is unreachable the limiter fails
open (logged) so an outage does not take the whole API down, except for the credential-facing
scopes in `FAIL_CLOSED_SCOPES` in production, which answer 503 instead of going unthrottled.
"""

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis

from app.core.config import Settings
from app.services.errors import RateLimitedError, RateLimiterUnavailableError

logger = logging.getLogger(__name__)

_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
_SPEC = re.compile(r"^(\d+)/(\d+)?(second|minute|hour|day)s?$")


FAIL_CLOSED_SCOPES = frozenset({"login_ip", "login_email", "refresh", "accept_invitation"})


@dataclass(frozen=True)
class Limit:
    count: int
    window_seconds: int


def parse_limit(spec: str) -> Limit:
    """ "10/minute", "8/15minute" -> Limit(10, 60), Limit(8, 900)."""
    match = _SPEC.match(spec.strip())
    if match is None or int(match[1]) < 1:
        raise ValueError(f"invalid rate limit {spec!r}; expected e.g. '10/minute' or '8/15minute'")
    window = int(match[2] or 1) * _UNITS[match[3]]
    if window < 1:
        raise ValueError(f"invalid rate limit window in {spec!r}")
    return Limit(int(match[1]), window)


class Backend(Protocol):
    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Counts one hit; returns (hits in the current window, seconds until it resets)."""
        ...

    async def close(self) -> None: ...


class MemoryBackend:
    def __init__(self) -> None:
        self._windows: dict[str, tuple[int, float]] = {}

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        now = time.monotonic()
        count, expires = self._windows.get(key, (0, 0.0))
        if expires <= now:
            count, expires = 0, now + window_seconds
        count += 1
        self._windows[key] = (count, expires)
        return count, max(1, int(expires - now) + 1)

    async def close(self) -> None:
        self._windows.clear()


class RedisBackend:
    def __init__(self, url: str) -> None:
        self._redis: Redis = Redis.from_url(url)  # connects lazily

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, window_seconds)
        ttl = await self._redis.ttl(key)
        if ttl < 0:  # key without expiry (crash between INCR and EXPIRE): repair it
            await self._redis.expire(key, window_seconds)
            ttl = window_seconds
        return int(count), int(ttl)

    async def close(self) -> None:
        await self._redis.aclose()


class RateLimiter:
    def __init__(
        self, backend: Backend, *, fail_closed_scopes: frozenset[str] = frozenset()
    ) -> None:
        self._backend = backend
        self._fail_closed_scopes = fail_closed_scopes

    async def check(self, scope: str, identity: str, limit: Limit) -> None:
        """Counts a hit for (scope, identity); raises RateLimitedError above the limit."""
        digest = hashlib.sha256(identity.lower().encode()).hexdigest()[:32]
        try:
            count, ttl = await self._backend.hit(f"rl:{scope}:{digest}", limit.window_seconds)
        except Exception as exc:
            logger.error("rate limiter unavailable", extra={"error_type": type(exc).__name__})
            if scope in self._fail_closed_scopes:
                raise RateLimiterUnavailableError from exc
            return
        if count > limit.count:
            raise RateLimitedError(ttl)

    async def close(self) -> None:
        await self._backend.close()


def build_rate_limiter(settings: Settings) -> RateLimiter:
    if settings.rate_limit_backend == "memory":
        return RateLimiter(MemoryBackend())
    return RateLimiter(
        RedisBackend(settings.rate_limit_redis_url or settings.celery_broker_url),
        fail_closed_scopes=FAIL_CLOSED_SCOPES if settings.is_production else frozenset(),
    )
