"""Rendered times are in the configured TZ, not UTC (the test DB runs with timezone=UTC like prod)."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, TIMEZONE, actions

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
