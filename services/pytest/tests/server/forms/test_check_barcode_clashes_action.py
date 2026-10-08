"""CheckBarcodeClashesAction: library selection and per-request/pool/experiment clash checks.

Routes (under ``/htmx/actions``):

- ``GET/POST /select-samples`` — pick libraries, then render the clash table for them.
  Insider-only, as legacy ``check_barcode_clashes_workflow.begin`` (the card only sits
  on the insider dashboard). The legacy POST only required a login; it is insider-only
  here too.
- ``GET /?seq_request_id=`` — READ on the request, grouped by pool.
- ``GET /?pool_id=`` — READ on the pool (FastAPI-only).
- ``GET /?experiment_id=`` — insider-only, grouped by lane.

Clashes are flagged on the row: Hamming distance 0 is an error, < 3 a warning.
"""

import json

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_experiment, create_library, create_pool, create_seq_request
from .._http import assert_form_invalid, get, post_form, post_form_csrf_mismatch

PREFIX = "/htmx/actions"
SELECT = f"{PREFIX}/select-samples"
RENDER = f"{PREFIX}/"

ERROR = "Hamming distance of 0 between barcode combination"
WARNING = "Small hamming distance between barcode combination"

I7_A, I5_A = "AAAAAAAA", "CCCCCCCC"
I7_B, I5_B = "GGGGGGGG", "TTTTTTTT"
I7_NEAR = "AAAAAAAT"  # one mismatch from I7_A


def _library(
    session: SyncSession, user, seq_request: models.SeqRequest, name: str,
    i7: str, i5: str | None, pool: models.Pool | None = None,
) -> models.Library:
    library = create_library(session, user, seq_request)
    library.name = name
    if pool is not None:
        library.pool_id = pool.id
    session.add(Q.library_index.create(
        name_i7=None, name_i5=None, sequence_i7=i7, sequence_i5=i5,
        index_kit_i7_id=None, index_kit_i5_id=None, orientation=None, library_id=library.id,
    ))
    session.flush()
    return library


def _pool(session: SyncSession, user, seq_request: models.SeqRequest, name: str) -> models.Pool:
    pool = create_pool(session, user, seq_request)
    pool.name = name
    session.flush()
    return pool


def _select(*library_ids: int) -> dict[str, str]:
    return {"library_ids": json.dumps(list(library_ids))}


# ── Select samples (GET/POST) ───────────────────────────────────────────────


def test_select_samples_renders_for_insider(client: TestClient, insider_token: str):
    response = get(client, SELECT, insider_token)

    assert response.status_code == 200
    assert "Check Barcode Clashes" in response.text
    assert 'name="csrf_token"' in response.text


def test_select_samples_denies_client(client: TestClient, user_token: str):
    """Legacy ``begin`` was insider-only; the generic card is only on the insider dashboard."""
    assert get(client, SELECT, user_token).status_code == 403


def test_submit_flags_identical_barcodes_as_error(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = create_seq_request(session, user)
    a = _library(session, user, seq_request, "Lib_A", I7_A, I5_A)
    b = _library(session, user, seq_request, "Lib_B", I7_A, I5_A)
    session.commit()

    response = post_form(client, SELECT, _select(a.id, b.id), token=insider_token)

    assert response.status_code == 200
    assert "Lib_A" in response.text and "Lib_B" in response.text
    assert ERROR in response.text


def test_submit_flags_close_barcodes_as_warning(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = create_seq_request(session, user)
    a = _library(session, user, seq_request, "Lib_A", I7_A, I5_A)
    b = _library(session, user, seq_request, "Lib_B", I7_NEAR, I5_A)
    session.commit()

    response = post_form(client, SELECT, _select(a.id, b.id), token=insider_token)

    assert response.status_code == 200
    assert ERROR not in response.text
    assert WARNING in response.text


def test_submit_distinct_barcodes_have_no_clash(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = create_seq_request(session, user)
    a = _library(session, user, seq_request, "Lib_A", I7_A, I5_A)
    b = _library(session, user, seq_request, "Lib_B", I7_B, I5_B)
    session.commit()

    response = post_form(client, SELECT, _select(a.id, b.id), token=insider_token)

    assert response.status_code == 200
    assert ERROR not in response.text
    assert WARNING not in response.text


def test_submit_single_index_libraries(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    """i7-only libraries are compared on i7 alone."""
    seq_request = create_seq_request(session, user)
    a = _library(session, user, seq_request, "Lib_A", I7_A, None)
    b = _library(session, user, seq_request, "Lib_B", I7_A, None)
    session.commit()

    response = post_form(client, SELECT, _select(a.id, b.id), token=insider_token)

    assert response.status_code == 200
    assert ERROR in response.text


def test_submit_empty_selection_is_rejected(client: TestClient, insider_token: str):
    response = post_form(client, SELECT, _select(), token=insider_token)
    assert_form_invalid(response)


def test_submit_denies_client(
    client: TestClient, session: SyncSession, user, user_2, user_token: str,
):
    """Legacy POST only required a login, so a client could read any library's barcodes."""
    own_request = create_seq_request(session, user)
    own = _library(session, user, own_request, "Own_Lib", I7_A, I5_A)
    foreign_request = create_seq_request(session, user_2)
    foreign = _library(session, user_2, foreign_request, "Foreign_Lib", I7_A, I5_A)
    session.commit()

    response = post_form(client, SELECT, _select(own.id, foreign.id), token=user_token)

    assert response.status_code == 403
    assert "Foreign_Lib" not in response.text


def test_submit_csrf_mismatch_rerenders(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    seq_request = create_seq_request(session, user)
    a = _library(session, user, seq_request, "Lib_A", I7_A, I5_A)
    session.commit()

    response = post_form_csrf_mismatch(client, SELECT, _select(a.id), token=insider_token)

    assert_form_invalid(response)
    assert ERROR not in response.text


# ── Render by sequencing request ────────────────────────────────────────────


@pytest.fixture
def request_with_pools(session: SyncSession, user):
    """Two pools; the same barcode appears once in each pool and twice in pool 1."""
    seq_request = create_seq_request(session, user)
    pool_1 = _pool(session, user, seq_request, "Pool_One")
    pool_2 = _pool(session, user, seq_request, "Pool_Two")
    _library(session, user, seq_request, "P1_Lib_A", I7_A, I5_A, pool_1)
    _library(session, user, seq_request, "P1_Lib_B", I7_B, I5_B, pool_1)
    _library(session, user, seq_request, "P2_Lib_A", I7_A, I5_A, pool_2)
    session.commit()
    return seq_request, pool_1, pool_2


def test_render_seq_request_groups_by_pool(
    client: TestClient, request_with_pools, user_token: str,
):
    """The same barcode in two different pools is not a clash."""
    seq_request, pool_1, pool_2 = request_with_pools

    response = get(client, RENDER, user_token, params={"seq_request_id": seq_request.id})

    assert response.status_code == 200
    assert "Pool: " in response.text
    for name in ("P1_Lib_A", "P1_Lib_B", "P2_Lib_A"):
        assert name in response.text
    assert ERROR not in response.text


def test_render_seq_request_flags_clash_within_pool(
    client: TestClient, session: SyncSession, user, request_with_pools, user_token: str,
):
    seq_request, pool_1, _ = request_with_pools
    _library(session, user, seq_request, "P1_Lib_C", I7_A, I5_A, pool_1)
    session.commit()

    response = get(client, RENDER, user_token, params={"seq_request_id": seq_request.id})

    assert response.status_code == 200
    assert ERROR in response.text


def test_render_seq_request_allows_insider(client: TestClient, request_with_pools, insider_token: str):
    seq_request, _, _ = request_with_pools
    response = get(client, RENDER, insider_token, params={"seq_request_id": seq_request.id})
    assert response.status_code == 200


def test_render_seq_request_denies_stranger(client: TestClient, request_with_pools, user_2_token: str):
    seq_request, _, _ = request_with_pools
    response = get(client, RENDER, user_2_token, params={"seq_request_id": seq_request.id})
    assert response.status_code == 403


def test_render_seq_request_unknown_is_404(client: TestClient, insider_token: str):
    """Legacy ``check_seq_request_barcode_clashes`` returned 404 for an unknown request."""
    response = get(client, RENDER, insider_token, params={"seq_request_id": 999999})
    assert response.status_code == 404


def test_render_seq_request_without_libraries(
    client: TestClient, session: SyncSession, user, user_token: str,
):
    """An empty request renders an empty table instead of failing."""
    seq_request = create_seq_request(session, user)
    session.commit()

    lenient = TestClient(client.app, raise_server_exceptions=False)
    response = get(lenient, RENDER, user_token, params={"seq_request_id": seq_request.id})

    assert response.status_code == 200


# ── Render by pool ──────────────────────────────────────────────────────────


def test_render_pool_flags_clash(
    client: TestClient, session: SyncSession, user, user_token: str,
):
    seq_request = create_seq_request(session, user)
    pool = _pool(session, user, seq_request, "Pool_One")
    _library(session, user, seq_request, "Lib_A", I7_A, I5_A, pool)
    _library(session, user, seq_request, "Lib_B", I7_A, I5_A, pool)
    session.commit()

    response = get(client, RENDER, user_token, params={"pool_id": pool.id})

    assert response.status_code == 200
    assert "Lib_A" in response.text and "Lib_B" in response.text
    assert ERROR in response.text


def test_render_pool_denies_stranger(
    client: TestClient, session: SyncSession, user, user_2_token: str,
):
    seq_request = create_seq_request(session, user)
    pool = _pool(session, user, seq_request, "Pool_One")
    _library(session, user, seq_request, "Lib_A", I7_A, I5_A, pool)
    session.commit()

    assert get(client, RENDER, user_2_token, params={"pool_id": pool.id}).status_code == 403


# ── Render by experiment ────────────────────────────────────────────────────


@pytest.fixture
def experiment_with_lanes(session: SyncSession, user, insider):
    """Lane 1 holds pools 1+2 (clashing barcodes), lane 2 holds pool 3 (same barcode, alone)."""
    experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    session.flush()
    lanes = sorted(session.get_all(Q.lane.select(experiment_id=experiment.id), limit=None), key=lambda lane: lane.number)
    seq_request = create_seq_request(session, user)
    pools = [_pool(session, user, seq_request, f"Pool_{i}") for i in (1, 2, 3)]
    _library(session, user, seq_request, "L1_Lib_A", I7_A, I5_A, pools[0])
    _library(session, user, seq_request, "L1_Lib_B", I7_A, I5_A, pools[1])
    _library(session, user, seq_request, "L2_Lib_A", I7_A, I5_A, pools[2])
    for lane, pool in ((lanes[0], pools[0]), (lanes[0], pools[1]), (lanes[1], pools[2])):
        session.add(models.links.LanePoolLink(
            lane_id=lane.id, pool_id=pool.id, experiment_id=experiment.id, lane_num=lane.number,
        ))
    session.commit()
    return experiment


def test_render_experiment_groups_by_lane(
    client: TestClient, experiment_with_lanes, insider_token: str,
):
    response = get(client, RENDER, insider_token, params={"experiment_id": experiment_with_lanes.id})

    assert response.status_code == 200
    assert "Lane: " in response.text
    for name in ("L1_Lib_A", "L1_Lib_B", "L2_Lib_A"):
        assert name in response.text
    # Lane 1 clashes; lane 2 has the same barcode alone, which is fine.
    lane_2 = response.text.split('id="group-')[2]
    assert ERROR in response.text
    assert ERROR not in lane_2


def test_render_experiment_denies_client(
    client: TestClient, experiment_with_lanes, user_token: str,
):
    response = get(client, RENDER, user_token, params={"experiment_id": experiment_with_lanes.id})
    assert response.status_code == 403


def test_render_experiment_unknown_is_404(client: TestClient, insider_token: str):
    """Legacy ``check_experiment_barcode_clashes`` returned 404 for an unknown experiment."""
    lenient = TestClient(client.app, raise_server_exceptions=False)
    response = get(lenient, RENDER, insider_token, params={"experiment_id": 999999})
    assert response.status_code == 404


# ── Render without context ──────────────────────────────────────────────────


def test_render_without_context_is_bad_request(client: TestClient, insider_token: str):
    assert get(client, RENDER, insider_token).status_code == 400
