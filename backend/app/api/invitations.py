from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.api.deps import CurrentUser, SessionDep, SettingsDep, limit_per_user
from app.schemas.care import InvitationCreate, InvitationCreated
from app.services import invitations as service
from app.services.errors import ConflictError, NotFoundError, PermissionDeniedError

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post(
    "", status_code=status.HTTP_201_CREATED, dependencies=[Depends(limit_per_user("invite"))]
)
async def create_invitation(
    session: SessionDep,
    settings: SettingsDep,
    inviter: CurrentUser,
    data: Annotated[InvitationCreate, Body()],
) -> InvitationCreated:
    try:
        invitation, token = await service.create_invitation(
            session,
            settings,
            inviter,
            email=data.email,
            role=data.role,
            clinician_id=data.clinician_id,
        )
    except PermissionDeniedError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role") from None
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinician not found") from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.message) from None
    return InvitationCreated(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        token=token,
    )
