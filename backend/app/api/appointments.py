import uuid
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Response, status

from app.api.deps import CurrentClient, CurrentClinician, SessionDep
from app.models import Appointment
from app.schemas.planning import AppointmentCreate, AppointmentRead, AppointmentUpdate
from app.services import appointments as service
from app.services.errors import NotFoundError

router = APIRouter(tags=["appointments"])


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")


def _read(appointment: Appointment, clinician_name: str | None = None) -> AppointmentRead:
    read = AppointmentRead.model_validate(appointment)
    read.clinician_name = clinician_name
    return read


def _changes(data: AppointmentUpdate) -> dict[str, object]:
    """Only the fields that were sent (they cannot be cleared)."""
    sent = data.model_dump(exclude_unset=True)
    return {k: v for k, v in sent.items() if v is not None}


# --- Client: read-only ------------------------------------------------------------------


@router.get("/appointments")
async def list_appointments(session: SessionDep, client: CurrentClient) -> list[AppointmentRead]:
    return [_read(a, name) for a, name in await service.list_own(session, client)]


# --- Clinician: manages appointments of assigned clients -------------------------


@router.get("/clinician/clients/{client_id}/appointments")
async def list_client_appointments(
    session: SessionDep, clinician: CurrentClinician, client_id: uuid.UUID
) -> list[AppointmentRead]:
    try:
        rows = await service.list_for_client(session, clinician, client_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found") from None
    return [_read(a, name) for a, name in rows]


@router.post("/clinician/clients/{client_id}/appointments", status_code=status.HTTP_201_CREATED)
async def create_client_appointment(
    session: SessionDep,
    clinician: CurrentClinician,
    client_id: uuid.UUID,
    data: Annotated[AppointmentCreate, Body()],
) -> AppointmentRead:
    try:
        appointment = await service.create_for_client(
            session, clinician, client_id, data.kind, data.scheduled_at
        )
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found") from None
    return _read(appointment, clinician.display_name)


@router.patch("/clinician/appointments/{appointment_id}")
async def update_client_appointment(
    session: SessionDep,
    clinician: CurrentClinician,
    appointment_id: uuid.UUID,
    data: Annotated[AppointmentUpdate, Body()],
) -> AppointmentRead:
    try:
        appointment = await service.update_for_client(
            session, clinician, appointment_id, _changes(data)
        )
    except NotFoundError:
        raise _not_found() from None
    return _read(appointment, clinician.display_name)


@router.delete("/clinician/appointments/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client_appointment(
    session: SessionDep, clinician: CurrentClinician, appointment_id: uuid.UUID
) -> Response:
    try:
        await service.delete_for_client(session, clinician, appointment_id)
    except NotFoundError:
        raise _not_found() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
