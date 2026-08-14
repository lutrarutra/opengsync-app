from datetime import datetime, timedelta
from collections.abc import Sequence

from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions as exc, config

router = APIRouter(prefix="/events", tags=["events"])


def _calendar_events(
    session: SyncSession,
    start_date: datetime,
    end_date: datetime,
    *,
    load_seq_request: bool = False,
) -> Sequence[models.Event]:
    options = [orm.selectinload(models.Event.seq_request)] if load_seq_request else None
    return session.get_all(
        Q.event.select(start_date=start_date, end_date=end_date),
        order_by=models.Event.timestamp_utc.asc(),
        limit=None,
        options=options,
    )


def _events_by_day(
    events: Sequence[models.Event],
    start_date: datetime,
    end_date: datetime,
) -> dict[datetime, list[models.Event]]:
    calendar: dict[datetime, list[models.Event]] = {}
    it = start_date
    while it <= end_date:
        calendar[it] = []
        for event in events:
            if event.timestamp_utc.date() == it.date():
                calendar[it].append(event)
        it += timedelta(days=1)
    return calendar


@router.get("/render-month", dependencies=[Depends(dependencies.require_insider)])
def events_month(
    year: int | None = Query(default=None, ge=2020, le=2100, description="Year of the events to render"),
    month: int | None = Query(default=None, ge=1, le=12, description="Month of the events to render"),
    session: SyncSession = Depends(dependencies.db_session),
):
    now = config.settings.now()
    if month is None:
        month = now.month
    if year is None:
        year = now.year

    try:
        start_date = config.settings.datetime(year, month, 1)
        end_date = (
            config.settings.datetime(year, month + 1, 1)
            if start_date.month < 12
            else config.settings.datetime(year + 1, 1, 1)
        )
    except ValueError:
        raise exc.BadRequestException()

    start_date = start_date - timedelta(days=start_date.weekday())
    end_date = end_date + timedelta(days=6 - end_date.weekday())

    events = _calendar_events(session, start_date, end_date)
    calendar = _events_by_day(events, start_date, end_date)

    return responses.htmx_response(
        "components/calendar/month.html",
        year=year,
        month=month,
        events=events,
        month_name=config.settings.datetime(year, month, 1).strftime("%B"),
        prev_year=year if month > 1 else year - 1,
        prev_month=month - 1 if month > 1 else 12,
        next_year=year if month < 12 else year + 1,
        next_month=month + 1 if month < 12 else 1,
        today=now,
        calendar=calendar,
    )


@router.get("/render-week", dependencies=[Depends(dependencies.require_insider)])
def events_week(
    year: int | None = Query(default=None, ge=2020, le=2100, description="Year of the events to render"),
    week: int | None = Query(default=None, ge=1, le=53, description="Week number of the events to render"),
    session: SyncSession = Depends(dependencies.db_session),
):
    now = config.settings.now()
    if week is None:
        week = now.isocalendar().week
    if year is None:
        year = now.year

    try:
        week_start = datetime.fromisocalendar(year, week, 1)
        week_end = datetime.fromisocalendar(year, week, 7)
        start_date = config.settings.datetime(week_start.year, week_start.month, week_start.day)
        end_date = config.settings.datetime(week_end.year, week_end.month, week_end.day)
    except ValueError:
        raise exc.BadRequestException()

    events = _calendar_events(session, start_date, end_date)
    calendar = _events_by_day(events, start_date, end_date)

    show_weekend = any(
        day.weekday() in (5, 6) and day_events
        for day, day_events in calendar.items()
    )
    if not show_weekend:
        saturday = datetime.fromisocalendar(year, week, 6)
        sunday = datetime.fromisocalendar(year, week, 7)
        calendar.pop(config.settings.datetime(sunday.year, sunday.month, sunday.day), None)
        calendar.pop(config.settings.datetime(saturday.year, saturday.month, saturday.day), None)

    return responses.htmx_response(
        "components/calendar/week.html",
        year=year,
        week=week,
        events=events,
        prev_year=year if week > 1 else year - 1,
        prev_week=week - 1 if week > 1 else 52,
        next_year=year if week < 52 else year + 1,
        next_week=week + 1 if week < 52 else 1,
        month_name=start_date.strftime("%B"),
        today=now,
        calendar=calendar,
        event_type_legend=C.EventType.to_color_legend(),
    )


@router.get("/render-day", dependencies=[Depends(dependencies.require_insider)])
def events_day(
    year: int | None = Query(default=None, ge=2020, le=2100, description="Year of the events to render"),
    month: int | None = Query(default=None, ge=1, le=12, description="Month of the events to render"),
    day: int | None = Query(default=None, ge=1, le=31, description="Day of the events to render"),
    session: SyncSession = Depends(dependencies.db_session),
):
    now = config.settings.now()
    if day is None:
        day = now.day
    if month is None:
        month = now.month
    if year is None:
        year = now.year

    try:
        start_date = config.settings.datetime(year, month, day)
        end_date = start_date + timedelta(days=1)
    except ValueError:
        raise exc.BadRequestException()

    events = _calendar_events(session, start_date, end_date, load_seq_request=True)

    return responses.htmx_response(
        "components/calendar/day.html",
        year=year,
        month=month,
        day=day,
        events=events,
        date=start_date,
    )
