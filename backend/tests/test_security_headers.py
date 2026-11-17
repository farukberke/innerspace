from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


async def _get(settings: Settings, path: str) -> dict[str, str]:
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(path)
    return dict(r.headers)


async def test_basic_security_headers_on_every_response(test_settings: Settings) -> None:
    headers = await _get(test_settings, "/health")
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    # Dev/test keep /docs usable: no CSP, no HSTS.
    assert "content-security-policy" not in headers
    assert "strict-transport-security" not in headers


async def test_production_adds_csp_and_hsts(test_settings: Settings) -> None:
    prod = test_settings.model_copy(update={"app_env": "production"})
    headers = await _get(prod, "/health")
    assert headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert headers["strict-transport-security"].startswith("max-age=")


async def test_api_responses_are_not_cached(test_settings: Settings) -> None:
    api = await _get(test_settings, "/api/v1/auth/me")  # 401 also carries the headers
    assert api["cache-control"] == "no-store"
    assert api["x-frame-options"] == "DENY"
    assert "cache-control" not in await _get(test_settings, "/health")
