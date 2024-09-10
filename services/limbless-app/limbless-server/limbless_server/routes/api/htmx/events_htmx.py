from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from flask import Blueprint, render_template, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse
from .... import db, forms, logger, cache  # noqa

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

events_htmx = Blueprint("events_htmx", __name__, url_prefix="/api/hmtx/events/")


@events_htmx.route("/render_calendar_month/<int:year>/<int:month>", methods=["GET"])
@events_htmx.route("/render_calendar_month", methods=["GET"], defaults={"year": datetime.now().year, "month": datetime.now().month})
@login_required
@cache.cached(timeout=60, query_string=True)
def render_calendar_month(year: int, month: int):
    try:
        start_date = datetime(year, month, 1)
        end_date = datetime(year, month + 1, 1) if start_date.month < 12 else datetime(year + 1, 1, 1)
    except TypeError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    start_date = start_date - timedelta(days=start_date.weekday())
    end_date = end_date + timedelta(days=6 - end_date.weekday())

    events, _ = db.get_events(
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
        "components/calendar-month.html", year=year, month=month, events=events,
        month_name=datetime(year, month, 1).strftime("%B"),
        prev_year=year if month > 1 else year - 1,
        prev_month=month - 1 if month > 1 else 12,
        next_year=year if month < 12 else year + 1,
        next_month=month + 1 if month < 12 else 1,
        today=datetime.now(),
        calendar=calendar
    ))


@events_htmx.route("/render_calendar_day/<int:year>/<int:month>/<int:day>", methods=["GET"])
@events_htmx.route("/render_calendar_day", methods=["GET"], defaults={"year": datetime.now().year, "month": datetime.now().month, "day": datetime.now().day})
@db_session(db)
@login_required
def render_calendar_day(year: int, month: int, day: int):
    try:
        start_date = datetime(year, month, day)
        end_date = datetime(year, month, day) + timedelta(days=1)
    except TypeError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    events, _ = db.get_events(
        start_date=start_date, end_date=end_date, limit=None,
        sort_by="timestamp_utc", descending=False,
    )

    return make_response(render_template(
        "components/calendar-day.html", year=year, month=month, day=day, events=events,
        date=start_date
    ))