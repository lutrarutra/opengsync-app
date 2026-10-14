"""MergePoolsWorkflow: merge two or more pools into a new pool.

As legacy ``merge_pools_workflow``: started from a sequencing request (needs WRITE) or a lab
prep / no context (insider). Step 1 selects at least two pools of the context; step 2 names the
new pool (prefilled: summed requested reads, common status (else DRAFT) and contact), with
reads and pipet volume per source pool (stored as ``merge_ratios``). Completion moves the
libraries to the new pool and marks the sources REPOOLED. Barcode clashes are only shown.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_lab_prep, create_library, create_pool, create_seq_request
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form


def _url(client: TestClient, route: str) -> str:
    return client.app.url_path_for(f"MergePoolsWorkflow.{route}")  # type: ignore[attr-defined]


class Setup:
    """A request of ``user`` with pools a (2 libraries, 100 M reads) and b (1 library, 50 M reads)."""

    def __init__(self, session: SyncSession, user: models.User):
        self.session = session
        self.user = user
        self.seq_request = create_seq_request(session, user)
        self.a = self._pool(100.0, 2)
        self.b = self._pool(50.0, 1)
        session.commit()

    def _pool(self, reads: float, num_libraries: int) -> models.Pool:
        pool = create_pool(self.session, self.user, self.seq_request)
        pool.num_m_reads_requested = reads
        self.session.save(pool, flush=True)
        for _ in range(num_libraries):
            library = create_library(self.session, self.user, self.seq_request)
            library.pool_id = pool.id
            self.session.save(library, flush=True)
        return pool

    def params(self) -> dict:
        return {"seq_request_id": self.seq_request.id, "uuid": str(uuid.uuid4())}

    def reload(self, pool: models.Pool) -> models.Pool:
        self.session.expire_all()
        return self.session.get_one(Q.pool.select(id=pool.id))


@pytest.fixture
def setup(session: SyncSession, user) -> Setup:
    return Setup(session, user)


def _select(client: TestClient, token: str, params: dict, pools: list[models.Pool]):
    get(client, _url(client, "Begin"), token, params=params)
    return post_form(client, _url(client, "SelectSamplesForm.Submit"), {"selected_pool_ids": json.dumps([p.id for p in pools])}, token=token, params=params)


def _merge_payload(pools: list[models.Pool], name: str = "Merged Pool", **overrides: str) -> dict:
    payload = {
        "name": name, "pool_type": str(C.PoolType.EXTERNAL.id), "status": str(C.PoolStatus.DRAFT.id),
        "num_m_reads_requested": "150", "total_volume_ul": "40",
        "contact_name": "Contact Person", "contact_email": "contact@example.com", "contact_phone": "",
    }
    for i, pool in enumerate(pools):
        payload |= {f"pool_forms-{i}-pool_id": str(pool.id), f"pool_forms-{i}-num_m_reads_requested": str(pool.num_m_reads_requested), f"pool_forms-{i}-pipet": "20"}
    return payload | overrides


def _merge(client: TestClient, token: str, params: dict, payload: dict):
    return post_form(client, _url(client, "MergePoolsForm.Submit"), payload, token=token, params=params)


def _pools_named(session: SyncSession, name: str) -> list[models.Pool]:
    session.expire_all()
    return session.get_all(Q.pool.select().where(models.Pool.name == name), limit=None)


# ── Selection ───────────────────────────────────────────────────────────────


def test_two_pools_open_the_merge_step_prefilled(client: TestClient, setup: Setup, user_token: str):
    response = _select(client, user_token, setup.params(), [setup.a, setup.b])

    assert response.status_code == 200, response.text
    assert "Merge Pools" in response.text
    assert 'name="pool_forms-1-pipet"' in response.text
    assert 'value="150.0"' in response.text  # summed requested reads


def test_more_than_two_pools_can_be_merged(client: TestClient, setup: Setup, user_token: str):
    c = setup._pool(10.0, 1)
    setup.session.commit()
    params = setup.params()
    assert _select(client, user_token, params, [setup.a, setup.b, c]).status_code == 200

    response = _merge(client, user_token, params, _merge_payload([setup.a, setup.b, c]))

    assert_htmx_redirect(response, "/pools/")
    [merged] = _pools_named(setup.session, "Merged Pool")
    assert len(merged.libraries) == 4


@pytest.mark.parametrize("count", [0, 1])
def test_fewer_than_two_pools_are_rejected(client: TestClient, setup: Setup, user_token: str, count: int):
    response = _select(client, user_token, setup.params(), [setup.a, setup.b][:count])

    assert_form_invalid(response)


def test_pool_of_another_request_is_rejected(client: TestClient, session: SyncSession, setup: Setup, user, user_token: str):
    other = Setup(session, user)

    response = _select(client, user_token, setup.params(), [setup.a, other.a])

    assert response.status_code == 404


# ── Merge ───────────────────────────────────────────────────────────────────


def test_merge_moves_libraries_and_marks_sources_repooled(client: TestClient, session: SyncSession, setup: Setup, user, user_token: str):
    params = setup.params()
    _select(client, user_token, params, [setup.a, setup.b])

    response = _merge(client, user_token, params, _merge_payload([setup.a, setup.b], **{"pool_forms-0-pipet": "12.5"}))

    assert_htmx_redirect(response, "/pools/")
    assert_flash(response, "Pools Merged!", "success")
    [merged] = _pools_named(session, "Merged Pool")
    assert merged.seq_request_id == setup.seq_request.id
    assert merged.owner_id == user.id
    assert merged.num_m_reads_requested == 150.0
    assert len(merged.libraries) == 3
    assert merged.merge_ratios[str(setup.a.id)] == {"num_m_reads_requested": 100.0, "pipet_volume_ul": 12.5}
    for source in (setup.a, setup.b):
        source = setup.reload(source)
        assert source.status == C.PoolStatus.REPOOLED
        assert source.merged_to_pool_id == merged.id
        assert source.libraries == []
    assert Redis(connection_pool=client.app.state.redis_pool).keys(f"MergePoolsWorkflow:{params['uuid']}:*") == []  # type: ignore[attr-defined]


@pytest.mark.parametrize("overrides, error", [
    ({"name": "abc"}, None),
    ({"name": ""}, None),
    ({"contact_name": "", "contact_email": ""}, "Contact is required"),
    ({"pool_forms-0-pipet": ""}, None),
    ({"pool_forms-0-num_m_reads_requested": ""}, None),
    ({"total_volume_ul": ""}, None),
    ({"pool_forms-0-pipet": "0"}, "must be > 0"),
    ({"pool_forms-1-pipet": "-5"}, "must be > 0"),
    ({"pool_forms-0-num_m_reads_requested": "0"}, "must be > 0"),
    ({"pool_forms-1-num_m_reads_requested": "-10"}, "must be > 0"),
], ids=["short-name", "missing-name", "missing-contact", "missing-pipet", "missing-reads", "missing-volume",
        "zero-pipet", "negative-pipet", "zero-reads", "negative-reads"])
def test_invalid_merge_is_rejected_and_changes_nothing(
    client: TestClient, session: SyncSession, setup: Setup, user_token: str, overrides: dict, error: str | None,
):
    params = setup.params()
    _select(client, user_token, params, [setup.a, setup.b])

    response = _merge(client, user_token, params, _merge_payload([setup.a, setup.b]) | overrides)

    assert_form_invalid(response, error)
    assert _pools_named(session, overrides.get("name") or "Merged Pool") == []
    assert setup.reload(setup.a).status != C.PoolStatus.REPOOLED


def test_invalid_merge_rerenders_pools_and_submitted_values(client: TestClient, setup: Setup, user_token: str):
    """The error re-render still loads the pools (template context) but keeps the submitted rows."""
    params = setup.params()
    _select(client, user_token, params, [setup.a, setup.b])

    response = _merge(client, user_token, params, _merge_payload([setup.a, setup.b], name="ab") | {"pool_forms-0-pipet": "12.5"})

    assert_form_invalid(response)
    assert setup.a.name in response.text and setup.b.name in response.text
    assert 'name="pool_forms-1-pipet"' in response.text
    assert 'name="pool_forms-2-pipet"' not in response.text
    assert 'value="12.5"' in response.text


def test_name_of_another_own_pool_is_rejected(client: TestClient, session: SyncSession, setup: Setup, user_token: str):
    existing = setup._pool(1.0, 0)
    existing.name = "Taken Name"
    session.save(existing, flush=True)
    session.commit()
    params = setup.params()
    _select(client, user_token, params, [setup.a, setup.b])

    response = _merge(client, user_token, params, _merge_payload([setup.a, setup.b], name="Taken Name"))

    assert_form_invalid(response, "already has a pool with the same name")


def test_name_of_a_merged_pool_may_be_reused(client: TestClient, session: SyncSession, setup: Setup, user_token: str):
    params = setup.params()
    _select(client, user_token, params, [setup.a, setup.b])

    response = _merge(client, user_token, params, _merge_payload([setup.a, setup.b], name=setup.a.name))

    assert_htmx_redirect(response, "/pools/")


def test_pool_not_selected_cannot_be_merged(client: TestClient, session: SyncSession, setup: Setup, user, user_token: str):
    """The merge step only merges the pools chosen in the selection step."""
    other = Setup(session, user)
    params = setup.params()
    _select(client, user_token, params, [setup.a, setup.b])

    response = _merge(client, user_token, params, _merge_payload([setup.a, other.a]))

    assert_form_invalid(response, "do not match")
    assert setup.reload(other.a).status != C.PoolStatus.REPOOLED
    assert _pools_named(session, "Merged Pool") == []


def test_back_navigation_keeps_the_selection(client: TestClient, setup: Setup, user_token: str):
    params = setup.params()
    _select(client, user_token, params, [setup.a, setup.b])

    response = get(client, _url(client, "SelectSamplesForm.Previous"), user_token, params=params)

    assert response.status_code == 200, response.text
    assert json.dumps([setup.a.id, setup.b.id]) in response.text or (str(setup.a.id) in response.text and str(setup.b.id) in response.text)


def test_merge_without_workflow_state_is_rejected(client: TestClient, session: SyncSession, setup: Setup, user_token: str):
    params = setup.params()

    response = _merge(client, user_token, params, _merge_payload([setup.a, setup.b]))

    assert response.status_code == 400
    assert get(client, _url(client, "SelectSamplesForm.Previous"), user_token, params=params).status_code == 400
    assert _pools_named(session, "Merged Pool") == []


def test_merging_twice_is_rejected(client: TestClient, session: SyncSession, setup: Setup, user_token: str):
    params = setup.params()
    _select(client, user_token, params, [setup.a, setup.b])
    assert_htmx_redirect(_merge(client, user_token, params, _merge_payload([setup.a, setup.b])), "/pools/")

    response = _merge(client, user_token, params, _merge_payload([setup.a, setup.b], name="Second Merge"))

    assert response.status_code == 400
    assert _pools_named(session, "Second Merge") == []


# ── Access ──────────────────────────────────────────────────────────────────


def test_other_user_is_denied(client: TestClient, setup: Setup, user_2_token: str):
    assert get(client, _url(client, "Begin"), user_2_token, params=setup.params()).status_code == 403


def test_client_without_context_is_denied(client: TestClient, user_token: str):
    assert get(client, _url(client, "Begin"), user_token).status_code == 403


def test_lab_prep_context_is_insider_only(client: TestClient, session: SyncSession, insider, user_token: str, insider_token: str):
    lab_prep = create_lab_prep(session, insider)
    session.commit()

    assert get(client, _url(client, "Begin"), user_token, params={"lab_prep_id": lab_prep.id}).status_code == 403
    assert get(client, _url(client, "Begin"), insider_token, params={"lab_prep_id": lab_prep.id}).status_code == 200


def test_unknown_request_is_404(client: TestClient, user_token: str):
    assert get(client, _url(client, "Begin"), user_token, params={"seq_request_id": 999999}).status_code == 404
