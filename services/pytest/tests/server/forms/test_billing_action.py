"""BillingAction: select sequenced experiments and download the billing workbook.

Legacy ``billing_workflow`` was insider-only on every route; it redirected to a separate
``download`` route. The FastAPI action returns the ``.xlsx`` straight from the POST.

The workbook has three sheets: ``pools`` (one row per pool, with lane and flow-cell
share of the loaded reads), ``experiments`` and ``lanes``.
"""

import io
import json
from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_experiment, create_library, create_pool, create_seq_request
from .._http import assert_flash, assert_form_invalid, get, post_form, post_form_csrf_mismatch

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"
WORKFLOW = C.ExperimentWorkFlow.NOVASEQ_6K_S4_XP  # 4 lanes × 2000 M = 8000 M reads


def _path(client: TestClient) -> str:
    return str(client.app.url_path_for("BillingAction.Begin"))


def _select(*experiment_ids: int) -> dict[str, str]:
    return {"experiment_ids": json.dumps(list(experiment_ids))}


def _sheets(response) -> dict[str, pd.DataFrame]:
    return pd.read_excel(io.BytesIO(response.content), sheet_name=None, dtype=str, keep_default_na=False)


def _lanes(session: SyncSession, experiment: models.Experiment) -> list[models.Lane]:
    return sorted(session.get_all(Q.lane.select(experiment_id=experiment.id), limit=None), key=lambda lane: lane.number)


def _load(
    session: SyncSession, experiment: models.Experiment, lane: models.Lane, pool: models.Pool,
    num_m_reads: float | None,
) -> None:
    session.add(models.links.LanePoolLink(
        lane_id=lane.id, pool_id=pool.id, experiment_id=experiment.id, lane_num=lane.number,
        num_m_reads=num_m_reads,
    ))


@pytest.fixture
def billed_experiment(session: SyncSession, user, insider):
    """Lane 1: Pool_A 100 M + Pool_B 300 M. Lane 2: Pool_B 400 M. 800 M loaded in total."""
    experiment = create_experiment(session, insider, WORKFLOW)
    experiment.name = "EXP_1"
    experiment.status = C.ExperimentStatus.SEQUENCED
    session.flush()
    lane_1, lane_2 = _lanes(session, experiment)[:2]

    seq_request = create_seq_request(session, user)
    seq_request.billing_code = "BILL-42"
    pool_a = create_pool(session, user, seq_request)
    pool_a.name = "Pool_A"
    pool_b = create_pool(session, user, seq_request)
    pool_b.name = "Pool_B"
    for pool in (pool_a, pool_b):
        pool.experiment_id = experiment.id
        library = create_library(session, user, seq_request)
        library.pool_id = pool.id
    session.flush()

    _load(session, experiment, lane_1, pool_a, 100)
    _load(session, experiment, lane_1, pool_b, 300)
    _load(session, experiment, lane_2, pool_b, 400)
    session.commit()
    return experiment, seq_request, pool_a, pool_b


def _pool_row(pools: pd.DataFrame, name: str) -> pd.Series:
    rows = pools[pools["pool_name"] == name]
    assert len(rows) == 1, f"expected one row for {name}, got {len(rows)}"
    return rows.iloc[0]


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_allows_insider(client: TestClient, insider_token: str):
    response = get(client, _path(client), insider_token)

    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text


def test_render_denies_client(client: TestClient, user_token: str):
    assert get(client, _path(client), user_token).status_code == 403


# ── Submit: workbook ────────────────────────────────────────────────────────


def test_submit_returns_billing_workbook(client: TestClient, billed_experiment, insider_token: str):
    experiment, _, _, _ = billed_experiment

    response = post_form(client, _path(client), _select(experiment.id), token=insider_token)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(XLSX)
    filename = f"billing_{datetime.now().strftime('%Y%m%d')}.xlsx"
    assert f'filename="{filename}"' in response.headers["content-disposition"]
    assert set(_sheets(response)) == {"pools", "experiments", "lanes"}


def test_submit_pool_rows_have_lane_and_flowcell_share(
    client: TestClient, billed_experiment, insider_token: str,
):
    experiment, seq_request, _, _ = billed_experiment

    pools = _sheets(post_form(client, _path(client), _select(experiment.id), token=insider_token))["pools"]

    pool_a = _pool_row(pools, "Pool_A")
    assert pool_a["lanes"] == "1"
    assert float(pool_a["num_m_reads_loaded"]) == 100
    assert "25.000%" in pool_a["lane_share"]
    assert pool_a["flowcell_share"] == "12.500%"

    pool_b = _pool_row(pools, "Pool_B")
    assert pool_b["lanes"] == "1, 2"
    assert float(pool_b["num_m_reads_loaded"]) == 700
    assert "75.000%" in pool_b["lane_share"] and "100.000%" in pool_b["lane_share"]
    assert pool_b["flowcell_share"] == "87.500%"

    assert pool_a["experiment_name"] == "EXP_1"
    assert pool_a["billing_code"] == "BILL-42"
    assert pool_a["contact_name"] == seq_request.contact_person.name
    assert pool_a["billing_name"] == seq_request.billing_contact.name
    assert pool_a["num_libraries"] == "1"


def test_submit_experiment_and_lane_sheets(client: TestClient, billed_experiment, insider_token: str):
    experiment, _, _, _ = billed_experiment

    sheets = _sheets(post_form(client, _path(client), _select(experiment.id), token=insider_token))

    experiments = sheets["experiments"]
    assert list(experiments["experiment_name"]) == ["EXP_1"]
    assert experiments.iloc[0]["num_lanes"] == "4"
    assert experiments.iloc[0]["num_pools"] == "2"
    assert float(experiments.iloc[0]["loaded_m_reads"]) == 800

    lanes = sheets["lanes"].set_index("lane")
    assert len(lanes) == 4
    assert float(lanes.loc["1", "num_m_reads_loaded"]) == 400
    assert lanes.loc["1", "pools"] == "Pool_A, Pool_B"
    assert float(lanes.loc["2", "num_m_reads_loaded"]) == 400
    assert lanes.loc["3", "num_pools"] == "0"


def test_submit_flags_experiment_below_capacity(client: TestClient, billed_experiment, insider_token: str):
    experiment, _, _, _ = billed_experiment

    pools = _sheets(post_form(client, _path(client), _select(experiment.id), token=insider_token))["pools"]

    assert all("below flow cell capacity" in info for info in pools["info"])


def test_submit_flags_experiment_over_capacity(
    client: TestClient, session: SyncSession, billed_experiment, insider_token: str,
):
    experiment, _, pool_a, _ = billed_experiment
    link = session.get_one(Q.links.get_laned_pool_link(experiment_id=experiment.id, lane_num=1, pool_id=pool_a.id))
    link.num_m_reads = 9000
    session.commit()

    pools = _sheets(post_form(client, _path(client), _select(experiment.id), token=insider_token))["pools"]

    assert all("exceeds flow cell capacity" in info for info in pools["info"])


def test_submit_flags_pool_with_missing_loaded_reads(
    client: TestClient, session: SyncSession, billed_experiment, insider_token: str,
):
    experiment, _, pool_a, _ = billed_experiment
    link = session.get_one(Q.links.get_laned_pool_link(experiment_id=experiment.id, lane_num=1, pool_id=pool_a.id))
    link.num_m_reads = None
    session.commit()

    pools = _sheets(post_form(client, _path(client), _select(experiment.id), token=insider_token))["pools"]

    pool_a_row = _pool_row(pools, "Pool_A")
    assert "Some lanes are missing number of loaded reads" in pool_a_row["info"]
    assert pool_a_row["num_m_reads_loaded"] == ""
    assert pool_a_row["flowcell_share"] == ""


def test_submit_flags_pool_mixing_requests(
    client: TestClient, session: SyncSession, user, billed_experiment, insider_token: str,
):
    """A pool without a request whose libraries come from two requests has no billing contact."""
    experiment, seq_request, _, _ = billed_experiment
    other_request = create_seq_request(session, user)
    mixed = create_pool(session, user, seq_request)
    mixed.name = "Pool_Mixed"
    mixed.seq_request_id = None
    mixed.experiment_id = experiment.id
    for request in (seq_request, other_request):
        library = create_library(session, user, request)
        library.pool_id = mixed.id
    session.flush()
    _load(session, experiment, _lanes(session, experiment)[2], mixed, 200)
    session.commit()

    pools = _sheets(post_form(client, _path(client), _select(experiment.id), token=insider_token))["pools"]

    row = _pool_row(pools, "Pool_Mixed")
    assert "Libraries in pool are from different requests" in row["info"]
    assert row["billing_name"] == ""
    assert row["billing_code"] == ""


def test_submit_pool_without_request_uses_library_request(
    client: TestClient, session: SyncSession, user, billed_experiment, insider_token: str,
):
    """A pool without a request whose libraries share one request bills that request."""
    experiment, seq_request, _, _ = billed_experiment
    pool = create_pool(session, user, seq_request)
    pool.name = "Pool_Lab"
    pool.seq_request_id = None
    pool.experiment_id = experiment.id
    library = create_library(session, user, seq_request)
    library.pool_id = pool.id
    session.flush()
    _load(session, experiment, _lanes(session, experiment)[2], pool, 200)
    session.commit()

    pools = _sheets(post_form(client, _path(client), _select(experiment.id), token=insider_token))["pools"]

    row = _pool_row(pools, "Pool_Lab")
    assert row["billing_code"] == "BILL-42"
    assert "different requests" not in row["info"]


def test_submit_multiple_experiments(
    client: TestClient, session: SyncSession, insider, billed_experiment, insider_token: str,
):
    experiment, _, _, _ = billed_experiment
    empty = create_experiment(session, insider, WORKFLOW)
    empty.name = "EXP_0"
    empty.status = C.ExperimentStatus.SEQUENCED
    session.commit()

    sheets = _sheets(post_form(client, _path(client), _select(experiment.id, empty.id), token=insider_token))

    assert list(sheets["experiments"]["experiment_name"]) == ["EXP_1", "EXP_0"]
    assert set(sheets["pools"]["experiment_name"]) == {"EXP_1"}
    assert len(sheets["lanes"]) == 8


def test_submit_does_not_mutate(
    client: TestClient, session: SyncSession, billed_experiment, insider_token: str,
):
    experiment, _, pool_a, _ = billed_experiment

    post_form(client, _path(client), _select(experiment.id), token=insider_token)

    session.expire_all()
    reloaded = session.get_one(Q.experiment.select(id=experiment.id))
    assert reloaded.status == C.ExperimentStatus.SEQUENCED
    assert session.get_one(Q.pool.select(id=pool_a.id)).experiment_id == experiment.id


# ── Submit: validation and access ───────────────────────────────────────────


def test_submit_empty_selection_is_rejected(client: TestClient, insider_token: str):
    response = post_form(client, _path(client), _select(), token=insider_token)
    assert_form_invalid(response)


def test_submit_unknown_experiment_is_404(client: TestClient, insider_token: str):
    """Legacy raised ``NotFoundException`` for an unknown experiment ID."""
    response = post_form(client, _path(client), _select(999999), token=insider_token)
    assert response.status_code == 404


def test_submit_denies_client(client: TestClient, billed_experiment, user_token: str):
    experiment, _, _, _ = billed_experiment
    response = post_form(client, _path(client), _select(experiment.id), token=user_token)
    assert response.status_code == 403


def test_submit_csrf_mismatch_rerenders(client: TestClient, billed_experiment, insider_token: str):
    experiment, _, _, _ = billed_experiment

    response = post_form_csrf_mismatch(client, _path(client), _select(experiment.id), token=insider_token)

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert not response.headers["content-type"].startswith(XLSX)
