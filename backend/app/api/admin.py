import uuid
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Response, status

from app.api.deps import CurrentOrgAdmin, SessionDep, SettingsDep
from app.models import UserRole
from app.schemas.care import AssignmentCreate, AssignmentRead, UserRead, UserStatusUpdate
from app.services import demo
from app.services import people as service
from app.services.errors import ConflictError, NotFoundError

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(
    session: SessionDep, admin: CurrentOrgAdmin, role: UserRole | None = None
) -> list[UserRead]:
    return [UserRead.model_validate(u) for u in await service.list_users(session, admin, role)]


@router.patch("/users/{user_id}")
async def update_user_status(
    session: SessionDep,
    settings: SettingsDep,
    admin: CurrentOrgAdmin,
    user_id: uuid.UUID,
    data: Annotated[UserStatusUpdate, Body()],
) -> UserRead:
    protected = await demo.protected_ids(session, settings)
    try:
        user = await service.set_user_active(
            session, admin, user_id, data.is_active, protected_ids=protected
        )
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found") from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.message) from None
    return UserRead.model_validate(user)


@router.get("/assignments")
async def list_assignments(session: SessionDep, admin: CurrentOrgAdmin) -> list[AssignmentRead]:
    items = await service.list_assignments(session, admin)
    return [AssignmentRead.model_validate(a) for a in items]


@router.post("/assignments", status_code=status.HTTP_201_CREATED)
async def create_assignment(
    session: SessionDep, admin: CurrentOrgAdmin, data: Annotated[AssignmentCreate, Body()]
) -> AssignmentRead:
    try:
        assignment = await service.create_assignment(
            session, admin, data.clinician_id, data.client_id
        )
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinician or client not found") from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.message) from None
    return AssignmentRead.model_validate(assignment)


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    session: SessionDep, settings: SettingsDep, admin: CurrentOrgAdmin, assignment_id: uuid.UUID
) -> Response:
    protected = await demo.protected_ids(session, settings)
    try:
        await service.delete_assignment(session, admin, assignment_id, protected_ids=protected)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found") from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.message) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
