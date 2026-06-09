from datetime import datetime
import sqlalchemy as sa
from sqlalchemy import sql

from ..models import Event
from ..categories import EventType


def create(
    title: str, timestamp_utc: datetime, type: EventType,
    user_id: int, note: str | None = None
) -> Event:
    event = Event(
        title=title.strip(),
        timestamp_utc=timestamp_utc,
        type_id=type.id,
        note=note,
        creator_id=user_id,
    )
    return event


def select(
    id: int | None = None,
    type: EventType | None = None,
    type_in: list[EventType] | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    statement: sql.Select[tuple[Event]] = sa.select(Event),
) -> sql.Select[tuple[Event]]:
    if id is not None:
        statement = statement.where(Event.id == id)
    if type is not None:
        statement = statement.where(Event.type_id == type.id)
    if type_in is not None:
        statement = statement.where(Event.type_id.in_([t.id for t in type_in]))
    if start_date is not None:
        statement = statement.where(Event.timestamp_utc >= start_date)
    if end_date is not None:
        statement = statement.where(Event.timestamp_utc <= end_date)

    return statement