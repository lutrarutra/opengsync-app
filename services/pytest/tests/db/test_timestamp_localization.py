"""Timestamps are stored as UTC and must render in the configured TZ, regardless of the
timezone Postgres hands them back in (prod runs the DB with timezone = UTC)."""
from datetime import datetime, timezone

import pytest

from opengsync_db import TIMEZONE, models

UTC_TS = datetime(2026, 7, 1, 22, 30, tzinfo=timezone.utc)


def _expected(fmt: str) -> str:
    return UTC_TS.astimezone(TIMEZONE).strftime(fmt)


def test_test_env_is_not_utc():
    # otherwise the assertions below can't tell localized from raw UTC
    assert UTC_TS.astimezone(TIMEZONE).utcoffset().total_seconds() != 0


def test_pool_dilution_timestamp_is_localized():
    dilution = models.PoolDilution(timestamp_utc=UTC_TS)
    assert dilution.timestamp_str() == _expected("%Y-%m-%d %H:%M")
    assert dilution.timestamp.utcoffset() == UTC_TS.astimezone(TIMEZONE).utcoffset()


@pytest.mark.parametrize("model", [models.Sample, models.Library, models.Pool])
def test_timestamp_stored_str_is_localized(model):
    obj = model(timestamp_stored_utc=UTC_TS)
    assert obj.timestamp_stored_str == _expected("%Y-%m-%d %H:%M:%S")


@pytest.mark.parametrize("model", [models.Sample, models.Library, models.Pool])
def test_timestamp_stored_str_empty_when_missing(model):
    assert model(timestamp_stored_utc=None).timestamp_stored_str == ""
