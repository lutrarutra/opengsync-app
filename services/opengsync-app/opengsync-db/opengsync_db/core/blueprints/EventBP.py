from datetime import datetime
import math
from typing import Optional

from ... import models, PAGE_LIMIT
from ...categories import EventTypeEnum
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class EventBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, title: str, timestamp_utc: datetime, type: EventTypeEnum,
        user_id: int, note: Optional[str] = None, flush: bool = True
    ) -> models.Event:
        event = models.Event(
            title=title.strip(),
            timestamp_utc=timestamp_utc,
            type_id=type.id,
            note=note,
            creator_id=user_id,
        )
        self.db.session.add(event)

        if flush:
            self.db.flush()
        return event

    @DBBlueprint.transaction
    def get(self, event_id: int) -> models.Event | None:
        event = self.db.session.get(models.Event, event_id)
        return event

    @DBBlueprint.transaction
    def find(
        self, type: Optional[EventTypeEnum] = None,
        type_in: Optional[list[EventTypeEnum]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        count_pages: bool = False
    ) -> tuple[list[models.Event], int | None]:
        query = self.db.session.query(models.Event)

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
        return events, n_pages

    @DBBlueprint.transaction
    def update(self, event: models.Event):
        self.db.session.add(event)

    @DBBlueprint.transaction
    def delete(self, event_id: int, flush: bool = True):
        if (event := self.db.session.get(models.Event, event_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Event with id {event_id} does not exist")
        
        self.db.session.delete(event)

        if flush:
            self.db.flush()
        
