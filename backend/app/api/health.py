import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import SessionDep

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def liveness() -> dict[str, str]:
    """The process is up. Does not touch dependencies."""
    return {"status": "ok"}


@router.get("/health/ready", response_model=None)
async def readiness(session: SessionDep) -> dict[str, str] | JSONResponse:
    """The app can serve traffic: database reachable."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.warning("readiness_check_failed", exc_info=True)
        return JSONResponse(
            {"status": "unavailable"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    return {"status": "ok"}
