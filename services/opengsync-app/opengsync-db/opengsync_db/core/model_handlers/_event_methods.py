from datetime import datetime
import math
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from ...categories import EventTypeEnum
from .. import exceptions


def create_event(
    self: "DBHandler", title: str, timestamp_utc: datetime, type: EventTypeEnum,
    user_id: int, note: Optional[str] = None, flush: bool = True
) -> models.Event:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    event = models.Event(
        title=title.strip(),
        timestamp_utc=timestamp_utc,
        type_id=type.id,
        note=note,
        creator_id=user_id,
    )
    
    self.session.add(event)

    if flush:
        self.flush()
    
    if not persist_session:
        self.close_session()
    return event


def get_event(self: "DBHandler", event_id: int) -> models.Event | None:
    if not (persist_session := self._session is not None):
        self.open_session()
    
    event = self.session.get(models.Event, event_id)
    
    if not persist_session:
        self.close_session()
    return event


def get_events(
    self: "DBHandler", type: Optional[EventTypeEnum] = None,
    type_in: Optional[list[EventTypeEnum]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int | None = PAGE_LIMIT, offset: int | None = None,
    sort_by: Optional[str] = None, descending: bool = False,
    count_pages: bool = False
) -> tuple[list[models.Event], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()
    
    query = self.session.query(models.Event)

    if type is not None:
        query = query.where(models.Event.type_id == type.id)
    if type_in is not None:
        query = query.where(models.Event.type_id.in_([t.id for t in type_in]))
    if start_date is not None:
        query = query.where(models.Event.timestamp_utc >= start_date)
    if end_date is not None:
        query = query.where(models.Event.timestamp_utc <= end_date)
    
    n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

    if sort_by is not None:
        attr = getattr(models.Event, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)
    
    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)
    
    events = query.all()
    
    if not persist_session:
        self.close_session()
    return events, n_pages


def update_event(self: "DBHandler", event: models.Event) -> models.Event:
    if not (persist_session := self._session is not None):
        self.open_session()
    
    self.session.add(event)
    
    if not persist_session:
        self.close_session()
    return event


def delete_event(self: "DBHandler", event_id: int, flush: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()
    
    if (event := self.session.get(models.Event, event_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Event with id {event_id} does not exist")
    
    self.session.delete(event)

    if flush:
        self.flush()
    
    if not persist_session:
        self.close_session()