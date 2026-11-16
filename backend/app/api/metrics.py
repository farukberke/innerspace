import secrets

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import SettingsDep
from app.core.metrics import METRICS

router = APIRouter(include_in_schema=False)


@router.get("/metrics")
async def metrics(request: Request, settings: SettingsDep) -> Response:
    """Prometheus metrics. Disabled (404) unless METRICS_TOKEN is set; then it needs
    `Authorization: Bearer <token>`. Contains no user content."""
    if settings.metrics_token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    expected = f"Bearer {settings.metrics_token.get_secret_value()}"
    given = request.headers.get("Authorization", "")
    if not secrets.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Response(METRICS.render(), media_type="text/plain; version=0.0.4")
