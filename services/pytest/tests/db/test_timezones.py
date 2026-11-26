"""App timezone handling in opengsync_db.

- One source of truth: ``opengsync_db.TIMEZONE`` (TZ env var, else the host zone, else UTC).
- Stored: every timestamp is a UTC instant, whatever TimeZone the Postgres session uses.
- Converted: ``localize`` (stored UTC -> local, for display) and ``to_utc`` (naive local input -> UTC).

The `vienna` fixture pins the zone so the expected local times are concrete.
"""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa

import opengsync_db
from opengsync_db import SyncSession, models, queries as Q, categories as C, localize, to_utc, utc_now

from .create_units import create_user, create_seq_request

UTC = dt.timezone.utc
SUMMER_UTC = dt.datetime(2026, 7, 1, 22, 30, tzinfo=UTC)   # 2026-07-02 00:30 CEST (UTC+2)
WINTER_UTC = dt.datetime(2026, 1, 15, 23, 30, tzinfo=UTC)  # 2026-01-16 00:30 CET (UTC+1)


def _set_session_timezone(session: SyncSession, name: str) -> None:
    """Postgres returns timestamptz values in the session's TimeZone. SET LOCAL lasts until the
    transaction ends, so callers flush instead of committing afterwards."""
    session.execute(sa.text(f"SET LOCAL TIME ZONE '{name}'"))


# ── Resolution ────────────────────────────────────────────────────────────────

def test_tz_env_var_is_used(monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    assert opengsync_db.resolve_timezone_name() == "America/New_York"


def test_posix_colon_prefix_is_stripped(monkeypatch):
    monkeypatch.setenv("TZ", ":Europe/Vienna")
    assert opengsync_db.resolve_timezone_name() == "Europe/Vienna"


@pytest.mark.parametrize("value", [None, "", "  "])
def test_unset_or_empty_tz_falls_back_to_host_zone(monkeypatch, value):
    # compose passes TZ=${TIMEZONE}, which is an empty string when TIMEZONE is unset
    import tzlocal
    if value is None:
        monkeypatch.delenv("TZ", raising=False)
    else:
        monkeypatch.setenv("TZ", value)
    monkeypatch.setattr(tzlocal, "get_localzone_name", lambda: "Asia/Tokyo")
    assert opengsync_db.resolve_timezone_name() == "Asia/Tokyo"


def test_no_host_zone_falls_back_to_utc(monkeypatch):
    import tzlocal
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(tzlocal, "get_localzone_name", lambda: None)
    assert opengsync_db.resolve_timezone_name() == "UTC"


def test_timezone_matches_its_name():
    assert opengsync_db.TIMEZONE == ZoneInfo(opengsync_db.TIMEZONE_NAME)


# ── Conversions ───────────────────────────────────────────────────────────────

def test_localize_converts_utc_to_local_time(vienna):
    assert localize(SUMMER_UTC).replace(tzinfo=None) == dt.datetime(2026, 7, 2, 0, 30)
    assert localize(WINTER_UTC).replace(tzinfo=None) == dt.datetime(2026, 1, 16, 0, 30)
    assert localize(SUMMER_UTC).tzinfo == vienna


def test_localize_takes_naive_values_as_utc(vienna):
    assert localize(SUMMER_UTC.replace(tzinfo=None)) == SUMMER_UTC


def test_localize_explicit_timezone():
    assert localize(SUMMER_UTC, "America/New_York").replace(tzinfo=None) == dt.datetime(2026, 7, 1, 18, 30)


def test_to_utc_takes_naive_values_as_local_time(vienna):
    stored = to_utc(dt.datetime(2026, 7, 2, 0, 30))
    assert stored == SUMMER_UTC
    assert stored.utcoffset() == dt.timedelta(0)
    assert to_utc(dt.datetime(2026, 1, 16, 0, 30)) == WINTER_UTC


def test_to_utc_keeps_the_instant_of_aware_values(vienna):
    stored = to_utc(SUMMER_UTC.astimezone(ZoneInfo("America/New_York")))
    assert stored == SUMMER_UTC
    assert stored.utcoffset() == dt.timedelta(0)


def test_localize_and_to_utc_round_trip(vienna):
    for moment in (SUMMER_UTC, WINTER_UTC):
        assert to_utc(localize(moment).replace(tzinfo=None)) == moment


def test_utc_now_is_aware_utc():
    now = utc_now()
    assert now.utcoffset() == dt.timedelta(0)
    assert abs(now - dt.datetime.now(UTC)) < dt.timedelta(seconds=5)


def test_model_properties_render_local_time(vienna):
    assert models.Event(timestamp_utc=SUMMER_UTC).timestamp_str() == "2026-07-02 00:30"
    assert models.Comment(timestamp_utc=WINTER_UTC).timestamp.replace(tzinfo=None) == dt.datetime(2026, 1, 16, 0, 30)
    assert models.Sample(timestamp_stored_utc=SUMMER_UTC).timestamp_stored_str == "2026-07-02 00:30:00"


# ── Storage ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("session_tz", ["UTC", "America/New_York", "Asia/Tokyo"])
def test_timestamps_are_stored_as_utc_whatever_the_session_timezone(session: SyncSession, vienna, session_tz: str):
    user = create_user(session)
    _set_session_timezone(session, session_tz)

    event = Q.event.create(title="tz", timestamp_utc=SUMMER_UTC, type=C.EventType.SAMPLE_SUBMISSION, user_id=user.id)
    session.add(event)
    session.flush()

    raw_utc = session.scalar(
        sa.text("SELECT to_char(timestamp_utc AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') FROM event WHERE id = :id"),
        {"id": event.id},
    )
    assert raw_utc == "2026-07-01 22:30"

    session.expire(event)
    assert event.timestamp_utc == SUMMER_UTC  # same instant, whatever offset it comes back with
    assert event.timestamp_str() == "2026-07-02 00:30"


def test_column_defaults_are_utc(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    comment = session.save(Q.comment.create(text="tz", author=user, seq_request_id=seq_request.id), flush=True)
    assert comment.timestamp_utc.utcoffset() == dt.timedelta(0)
    assert abs(comment.timestamp_utc - dt.datetime.now(UTC)) < dt.timedelta(seconds=30)


# ── Token expiration in SQL ───────────────────────────────────────────────────
# The SQL side of the `expiration` hybrid used to strip the zone (timezone('UTC', created_utc)),
# so Postgres read it in the session's TimeZone when comparing it with now().

def _tokens(session: SyncSession, make) -> tuple:
    now = dt.datetime.now(UTC)
    valid = make()
    valid.created_utc = now - dt.timedelta(minutes=30)
    expired = make()
    expired.created_utc = now - dt.timedelta(minutes=120)
    session.add_all([valid, expired])
    session.commit()
    return valid, expired


@pytest.mark.parametrize("session_tz", ["UTC", "America/New_York", "Asia/Tokyo"])
def test_share_token_expiration_in_sql_matches_python(session: SyncSession, session_tz: str):
    user = create_user(session)
    valid, expired = _tokens(session, lambda: Q.share_token.create(owner=user, time_valid_min=60, paths=[]))
    expected = {valid.uuid: valid.expiration, expired.uuid: expired.expiration}
    _set_session_timezone(session, session_tz)

    ids = list(expected)
    rows = dict(session.execute(
        sa.select(models.ShareToken.uuid, models.ShareToken.expiration).where(models.ShareToken.uuid.in_(ids))
    ).all())
    assert rows == expected
    assert all(value.tzinfo is not None for value in rows.values())

    active = set(session.scalars(
        sa.select(models.ShareToken.uuid).where(models.ShareToken.uuid.in_(ids), models.ShareToken.expiration > sa.func.now())
    ))
    assert active == {valid.uuid}
    assert not valid.is_expired and expired.is_expired


@pytest.mark.parametrize("session_tz", ["UTC", "America/New_York", "Asia/Tokyo"])
def test_api_token_expiration_in_sql_matches_python(session: SyncSession, session_tz: str):
    user = create_user(session)
    valid, expired = _tokens(session, lambda: Q.api_token.create(owner=user, time_valid_min=60))
    expected = {valid.id: valid.expiration, expired.id: expired.expiration}
    _set_session_timezone(session, session_tz)

    ids = list(expected)
    rows = dict(session.execute(
        sa.select(models.APIToken.id, models.APIToken.expiration).where(models.APIToken.id.in_(ids))
    ).all())
    assert rows == expected

    active = set(session.scalars(
        sa.select(models.APIToken.id).where(models.APIToken.id.in_(ids), models.APIToken.expiration > sa.func.now())
    ))
    assert active == {valid.id}
    assert not valid.is_expired and expired.is_expired
