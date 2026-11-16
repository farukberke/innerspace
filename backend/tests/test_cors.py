import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


def _settings(test_settings: Settings, origins: str) -> Settings:
    return test_settings.model_copy(update={"cors_origins": origins})


async def _preflight(settings: Settings, origin: str) -> dict[str, str]:
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.options(
            "/api/v1/auth/login",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
    return dict(r.headers)


async def test_cors_allows_configured_origin(test_settings: Settings) -> None:
    headers = await _preflight(
        _settings(test_settings, "http://localhost:5173"), "http://localhost:5173"
    )
    assert headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_cors_rejects_other_origin(test_settings: Settings) -> None:
    headers = await _preflight(
        _settings(test_settings, "http://localhost:5173"), "http://evil.example"
    )
    assert "access-control-allow-origin" not in headers


async def test_cors_off_by_default(test_settings: Settings) -> None:
    headers = await _preflight(_settings(test_settings, ""), "http://localhost:5173")
    assert "access-control-allow-origin" not in headers


def test_cors_wildcard_rejected(test_settings: Settings) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({**test_settings.model_dump(), "cors_origins": "*"})
