import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_invitation_token, hash_password, new_invitation_token
from app.models import CareAssignment, Invitation, User, UserRole
from app.services import audit
from app.services.auth import normalize_email
from app.services.errors import (
    ConflictError,
    InvalidInvitationError,
    NotFoundError,
    PermissionDeniedError,
)


async def create_invitation(
    session: AsyncSession,
    settings: Settings,
    inviter: User,
    *,
    email: str,
    role: UserRole,
    clinician_id: uuid.UUID | None,
) -> tuple[Invitation, str]:
    """Invitations always belong to the inviter's own organization.

    - clinician: may invite clients only; the client is assigned to the inviting clinician.
    - org_admin: may invite clinicians or clients (clients optionally pre-assigned).
    """
    if inviter.role == UserRole.CLINICIAN:
        if role != UserRole.CLIENT:
            raise PermissionDeniedError
        clinician_id = inviter.id
    elif inviter.role == UserRole.ORG_ADMIN:
        if role == UserRole.ORG_ADMIN:
            raise PermissionDeniedError
        if role == UserRole.CLINICIAN:
            clinician_id = None
    else:
        raise PermissionDeniedError

    if clinician_id is not None:
        clinician = await session.scalar(
            select(User).where(
                User.id == clinician_id,
                User.organization_id == inviter.organization_id,
                User.role == UserRole.CLINICIAN,
                User.is_active.is_(True),
            )
        )
        if clinician is None:
            raise NotFoundError

    email = normalize_email(email)
    if await session.scalar(select(User.id).where(User.email == email)):
        raise ConflictError("A user with this e-mail already exists")

    token, token_hash = new_invitation_token()
    invitation = Invitation(
        organization_id=inviter.organization_id,
        invited_by_id=inviter.id,
        email=email,
        role=role,
        assign_clinician_id=clinician_id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.invitation_hours),
    )
    session.add(invitation)
    await session.flush()
    await audit.record(
        session,
        "invitation.create",
        organization_id=inviter.organization_id,
        actor_id=inviter.id,
        target_type="invitation",
        target_id=invitation.id,
        detail={"role": role.value},
    )
    await session.commit()
    return invitation, token


async def accept_invitation(
    session: AsyncSession, token: str, *, password: str, display_name: str
) -> User:
    """Consumes the token (single use) and creates the user in the invitation's org/role."""
    invitation = await session.scalar(
        select(Invitation)
        .where(Invitation.token_hash == hash_invitation_token(token))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if invitation is None or invitation.used_at is not None or invitation.expires_at <= now:
        raise InvalidInvitationError
    if await session.scalar(select(User.id).where(User.email == invitation.email)):
        raise InvalidInvitationError

    user = User(
        organization_id=invitation.organization_id,
        email=invitation.email,
        display_name=display_name.strip(),
        role=invitation.role,
        password_hash=await hash_password(password),
    )
    session.add(user)
    await session.flush()
    invitation.used_at = now
    if invitation.role == UserRole.CLIENT and invitation.assign_clinician_id is not None:
        session.add(
            CareAssignment(
                organization_id=user.organization_id,
                clinician_id=invitation.assign_clinician_id,
                client_id=user.id,
            )
        )
    await audit.record(
        session,
        "invitation.accept",
        organization_id=user.organization_id,
        actor_id=user.id,
        target_type="invitation",
        target_id=invitation.id,
        detail={"role": user.role.value},
    )
    await session.commit()
    return user
