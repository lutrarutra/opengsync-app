from datetime import datetime
import math
from typing import Optional

from ... import models, PAGE_LIMIT
from ...categories import EventTypeEnum
from .. import exceptions


def create_event(
    self, title: str, timestamp_utc: datetime, type: EventTypeEnum,
    user_id: int, note: Optional[str] = None,
) -> models.Event:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")
    
    event = models.Event(
        title=title.strip(),
        timestamp_utc=timestamp_utc,
        type_id=type.id,
        note=note,
        user_id=user_id,
    )
    
    self._session.add(event)
    self._session.commit()
    self._session.refresh(event)
    
    if not persist_session:
        self.close_session()
    return event


def get_event(self, event_id: int) -> Optional[models.Event]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
    
    event = self._session.get(models.Event, event_id)
    
    if not persist_session:
        self.close_session()
    return event


def get_events(
    self, type: Optional[EventTypeEnum] = None,
    type_in: Optional[list[EventTypeEnum]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.Event], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
    
    query = self._session.query(models.Event)

    if type is not None:
        query = query.where(models.Event.type_id == type.id)
    if type_in is not None:
        query = query.where(models.Event.type_id.in_([t.id for t in type_in]))
    if start_date is not None:
        query = query.where(models.Event.timestamp_utc >= start_date)
    if end_date is not None:
        query = query.where(models.Event.timestamp_utc <= end_date)
    
    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

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


def update_event(self, event: models.Event) -> models.Event:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
    
    self._session.add(event)
    self._session.commit()
    self._session.refresh(event)
    
    if not persist_session:
        self.close_session()
    return event


def delete_event(self, event_id: int):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
    
    if (event := self._session.get(models.Event, event_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Event with id {event_id} does not exist")
    
    self._session.delete(event)
    self._session.commit()
    
    if not persist_session:
        self.close_session()