"""In-app reminders for the client (no notifications). Computed on request from the client's
own data only; calm wording, no streaks or scores.

"Tomorrow" and "yesterday" are calendar days in `Settings.reminder_timezone` (the client's
day), not rolling 24-hour windows."""

from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AfterSessionNote, Appointment, Summary, User


class ReminderKind(StrEnum):
    PREPARE_SUMMARY = "prepare_summary"
    AFTER_SESSION_NOTE = "after_session_note"


def _day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tz)
    return start.astimezone(UTC), end.astimezone(UTC)


async def compute(
    session: AsyncSession, client: User, timezone: str, now: datetime | None = None
) -> list[tuple[ReminderKind, Appointment]]:
    tz = ZoneInfo(timezone)
    today = (now or datetime.now(UTC)).astimezone(tz).date()
    result: list[tuple[ReminderKind, Appointment]] = []

    def _own(start: datetime, end: datetime):
        return select(Appointment).where(
            Appointment.client_id == client.id,
            Appointment.organization_id == client.organization_id,
            Appointment.scheduled_at >= start,
            Appointment.scheduled_at < end,
        )

    start, end = _day_bounds(today + timedelta(days=1), tz)
    upcoming = _own(start, end).where(
        ~exists().where(Summary.appointment_id == Appointment.id, Summary.client_id == client.id)
    )
    for appointment in (await session.scalars(upcoming.order_by(Appointment.scheduled_at))).all():
        result.append((ReminderKind.PREPARE_SUMMARY, appointment))

    start, end = _day_bounds(today - timedelta(days=1), tz)
    past = _own(start, end).where(
        ~exists().where(
            AfterSessionNote.client_id == client.id,
            AfterSessionNote.organization_id == client.organization_id,
            AfterSessionNote.created_at >= Appointment.scheduled_at,
        )
    )
    for appointment in (await session.scalars(past.order_by(Appointment.scheduled_at))).all():
        result.append((ReminderKind.AFTER_SESSION_NOTE, appointment))
    return result
