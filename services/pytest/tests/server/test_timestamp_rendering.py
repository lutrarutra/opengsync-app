"""Rendered times are in the configured TZ, not UTC (the test DB runs with timezone=UTC like prod)."""
import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient

import opengsync_db
from opengsync_db import SyncSession, TIMEZONE, actions, models

from server.core import config, templates
from server.routes.htmx.events import _events_by_day

from ..db.create_units import create_user, create_seq_request, create_pool
from ._http import get

UTC_TS = datetime(2026, 7, 1, 22, 30, tzinfo=timezone.utc)


def test_pool_dilution_table_renders_local_time(client: TestClient, session: SyncSession, insider_token: str):
    user = create_user(session)
    pool = create_pool(session, user, create_seq_request(session, user))
    actions.dilute_pool(session, pool, 1.0, user.id, None)
    session.refresh(pool)
    pool.dilutions[0].timestamp_utc = UTC_TS
    session.commit()

    response = get(client, f"/htmx/dilutions/render-table-page?pool_id={pool.id}", token=insider_token, htmx=True)
    assert response.status_code == 200
    assert UTC_TS.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M") in response.text
    assert UTC_TS.strftime("%Y-%m-%d %H:%M") not in response.text


# ── App timezone: one source, filters and calendar render local time ─────────
# The `vienna` fixture pins the zone (CEST = UTC+2 on these dates) so expected strings are concrete.

LOCAL = "2026-07-02 00:30"  # UTC_TS in Europe/Vienna: the next calendar day


def test_settings_timezone_is_the_db_package_timezone():
    assert config.settings.TIMEZONE is opengsync_db.TIMEZONE


def test_settings_follow_the_single_source(vienna):
    assert config.settings.TIMEZONE is vienna
    assert config.settings.now().utcoffset() == vienna.utcoffset(config.settings.now().replace(tzinfo=None))
    assert config.settings.datetime(2026, 7, 2, 0, 30).astimezone(timezone.utc) == UTC_TS


def test_format_datetime_filter(vienna):
    assert templates.format_datetime(UTC_TS) == LOCAL
    # naive values (seq run times from instrument files) are already local
    assert templates.format_datetime(datetime(2026, 7, 1, 22, 30)) == "2026-07-01 22:30"
    assert templates.format_datetime(None) == ""


def test_format_short_date_uses_the_local_day(vienna):
    assert templates.format_short_date(UTC_TS, format="%d.%m.%Y", other_year_format="%d.%m.%Y") == "02.07.2026"


def test_unix_time_filters_render_local_time(vienna):
    epoch = UTC_TS.timestamp()
    assert templates.format_timestamp(epoch) == LOCAL
    assert templates.from_timestamp(str(epoch)) == LOCAL
    assert templates.from_timestamp(None) == ""


def test_format_iso_filter(vienna):
    assert templates.format_iso(UTC_TS.isoformat()) == LOCAL
    # naive ISO strings (older JSON values) were written in local time
    assert templates.format_iso("2026-07-02T00:30:00") == LOCAL
    assert templates.format_iso("not a time") == "<error formatting time>"


def test_time_ago_filter():
    assert templates.time_ago(time.time() - 125) == "2 min ago"
    assert templates.time_ago(None) == "never"


def test_calendar_puts_events_on_their_local_day(vienna):
    event = models.Event(timestamp_utc=UTC_TS)  # 2026-07-01 in UTC, 2026-07-02 locally
    days = _events_by_day([event], config.settings.datetime(2026, 7, 1), config.settings.datetime(2026, 7, 3))
    by_date = {day.date().isoformat(): events for day, events in days.items()}
    assert by_date["2026-07-01"] == []
    assert by_date["2026-07-02"] == [event]
