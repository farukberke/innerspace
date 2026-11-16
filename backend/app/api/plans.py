import uuid
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, status

from app.api.deps import CurrentClient, CurrentClinician, SessionDep
from app.schemas.planning import PlanContent, PlanRead, SharedPlanRead
from app.services import plans as service
from app.services.errors import NotFoundError

router = APIRouter(tags=["plan"])


@router.get("/plan")
async def get_plan(session: SessionDep, client: CurrentClient) -> PlanRead:
    plan = await service.get_own(session, client)
    return PlanRead.model_validate(plan) if plan else PlanRead()


@router.put("/plan")
async def save_plan(
    session: SessionDep, client: CurrentClient, data: Annotated[PlanContent, Body()]
) -> PlanRead:
    return PlanRead.model_validate(await service.save_own(session, client, data))


@router.post("/plan/share")
async def share_plan(session: SessionDep, client: CurrentClient) -> PlanRead:
    try:
        plan = await service.set_shared(session, client, True)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Create your plan first") from None
    return PlanRead.model_validate(plan)


@router.post("/plan/unshare")
async def unshare_plan(session: SessionDep, client: CurrentClient) -> PlanRead:
    try:
        plan = await service.set_shared(session, client, False)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Create your plan first") from None
    return PlanRead.model_validate(plan)


@router.get("/clinician/clients/{client_id}/plan")
async def get_shared_plan(
    session: SessionDep, clinician: CurrentClinician, client_id: uuid.UUID
) -> SharedPlanRead:
    try:
        plan = await service.get_shared_with(session, clinician, client_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found") from None
    return SharedPlanRead.model_validate(plan)
