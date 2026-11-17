from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from app.api.deps import CurrentClient, SessionDep, SettingsDep, limit_per_user
from app.schemas.account import REMINDER_MESSAGES, AccountDelete, AccountExport, Reminder
from app.services import account as service
from app.services import reminders
from app.services.errors import InvalidCredentialsError

router = APIRouter(tags=["account"])


@router.get("/reminders")
async def get_reminders(
    session: SessionDep, settings: SettingsDep, client: CurrentClient
) -> list[Reminder]:
    items = await reminders.compute(session, client, settings.reminder_timezone)
    return [
        Reminder(
            kind=kind.value,
            message=REMINDER_MESSAGES[kind.value],
            appointment_id=appointment.id,
            scheduled_at=appointment.scheduled_at,
        )
        for kind, appointment in items
    ]


@router.get("/account/export", dependencies=[Depends(limit_per_user("export"))])
async def export_account(
    response: Response, session: SessionDep, client: CurrentClient
) -> AccountExport:
    """All of the caller's own data as a JSON download."""
    response.headers["Content-Disposition"] = 'attachment; filename="seansarasi-verilerim.json"'
    response.headers["Cache-Control"] = "no-store"
    return await service.export_data(session, client)


@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_per_user("account_delete"))],
)
async def delete_account(
    session: SessionDep, client: CurrentClient, data: Annotated[AccountDelete, Body()]
) -> None:
    """Permanent deletion of the caller's own account and data (password + typed "SİL")."""
    try:
        await service.delete_account(session, client, data.password)
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is incorrect") from None
