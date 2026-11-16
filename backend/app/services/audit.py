"""Audit trail. Records who did what to which object; never clinical content or e-mail/PII."""

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

logger = logging.getLogger("innerspace.audit")


async def record(
    session: AsyncSession,
    action: str,
    *,
    organization_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Adds the record to the caller's transaction (commits with the action itself)."""
    session.add(
        AuditLog(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
        )
    )
    logger.info(
        "audit",
        extra={"action": action, "actor_id": str(actor_id), "target_type": target_type},
    )
