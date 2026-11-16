import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
    # E-mails are globally unique, so an existing address in ANOTHER organization must not be
    # revealed: the invitation is created and only acceptance fails (generic error).
    existing_org = await session.scalar(select(User.organization_id).where(User.email == email))
    if existing_org == inviter.organization_id:
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
    # The people who vouched for this invitation must still be active.
    sponsor_ids = [invitation.invited_by_id]
    if invitation.assign_clinician_id is not None:
        sponsor_ids.append(invitation.assign_clinician_id)
    active = set(
        await session.scalars(
            select(User.id).where(User.id.in_(sponsor_ids), User.is_active.is_(True))
        )
    )
    if active != set(sponsor_ids):
        raise InvalidInvitationError

    user = User(
        organization_id=invitation.organization_id,
        email=invitation.email,
        display_name=display_name.strip(),
        role=invitation.role,
        password_hash=await hash_password(password),
    )
    session.add(user)
    invitation.used_at = now
    try:
        await session.flush()
        if invitation.role == UserRole.CLIENT and invitation.assign_clinician_id is not None:
            session.add(
                CareAssignment(
                    organization_id=user.organization_id,
                    clinician_id=invitation.assign_clinician_id,
                    client_id=user.id,
                    created_at=now,
                )
            )
            await session.flush()
    except IntegrityError:  # e.g. the e-mail was registered concurrently
        await session.rollback()
        raise InvalidInvitationError from None
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
