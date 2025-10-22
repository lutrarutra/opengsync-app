from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_htmx import make_response

from opengsync_db import models

from ... import db, logger  # noqa
from ...core import wrappers, exceptions

events_htmx = Blueprint("events_htmx", __name__, url_prefix="/htmx/events/")


@wrappers.htmx_route(events_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def render_calendar_month(current_user: models.User, year: int | None = None, month: int | None = None):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    try:
        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year
        start_date = datetime(year, month, 1)
        end_date = datetime(year, month + 1, 1) if start_date.month < 12 else datetime(year + 1, 1, 1)
    except TypeError:
        raise exceptions.BadRequestException()
    
    start_date = start_date - timedelta(days=start_date.weekday())
    end_date = end_date + timedelta(days=6 - end_date.weekday())

    events, _ = db.events.find(
        start_date=start_date, end_date=end_date, limit=None,
        sort_by="timestamp_utc", descending=False,
    )

    calendar = {}
    it = start_date
    while it <= end_date:
        calendar[it] = []
        for event in events:
            if event.timestamp_utc.date() == it.date():
                calendar[it].append(event)
        it += timedelta(days=1)

    return make_response(render_template(
        "components/calendar/month.html", year=year, month=month, events=events,
        month_name=datetime(year, month, 1).strftime("%B"),
        prev_year=year if month > 1 else year - 1,
        prev_month=month - 1 if month > 1 else 12,
        next_year=year if month < 12 else year + 1,
        next_month=month + 1 if month < 12 else 1,
        today=datetime.now(),
        calendar=calendar
    ))


@wrappers.htmx_route(events_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def render_calendar_week(current_user: models.User, year: int | None = None, week: int | None = None):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    try:
        if week is None:
            week = datetime.now().isocalendar().week
        if year is None:
            year = datetime.now().year
        start_date = datetime.fromisocalendar(year, week, 1)
        end_date = datetime.fromisocalendar(year, week, 7)
    except TypeError:
        raise exceptions.BadRequestException()

    events, _ = db.events.find(
        start_date=start_date, end_date=end_date, limit=None,
        sort_by="timestamp_utc", descending=False,
    )

    calendar = {}
    it = start_date
    show_weekend = False
    while it <= end_date:
        calendar[it] = []
        for event in events:
            if event.timestamp_utc.date() == it.date():
                calendar[it].append(event)
                if it.weekday() == 5 or it.weekday() == 6:
                    show_weekend = True
        it += timedelta(days=1)

    if not show_weekend:
        calendar.pop(datetime.fromisocalendar(year, week, 7))
        calendar.pop(datetime.fromisocalendar(year, week, 6))

    return make_response(render_template(
        "components/calendar/week.html",
        year=year, week=week, events=events,
        prev_year=year if week > 1 else year - 1,
        prev_week=week - 1 if week > 1 else 52,
        next_year=year if week < 52 else year + 1,
        next_week=week + 1 if week < 52 else 1,
        month_name=start_date.strftime("%B"),
        today=datetime.now(),
        calendar=calendar,
    ))


@wrappers.htmx_route(events_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def render_calendar_day(current_user: models.User, year: int | None = None, month: int | None = None, day: int | None = None):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    try:
        if day is None:
            day = datetime.now().day
        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year
        start_date = datetime(year, month, day)
        end_date = datetime(year, month, day) + timedelta(days=1)
    except TypeError:
        raise exceptions.BadRequestException()
    
    events, _ = db.events.find(
        start_date=start_date, end_date=end_date, limit=None,
        sort_by="timestamp_utc", descending=False,
    )

    return make_response(render_template(
        "components/calendar/day.html", year=year, month=month, day=day, events=events,
        date=start_date
    ))