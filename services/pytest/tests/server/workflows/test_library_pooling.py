"""LibraryPoolingWorkflow: assign a lab prep's libraries to pools.

As legacy ``library_pooling_workflow``: insider-only. Step 1 is a spreadsheet (library as
"name [id]", pool, M reads requested) of the prep's libraries; the library must be one of
the prep's, ``t`` (control) is not allowed for a library. M reads requested is
required (>= 0) for pooled rows and must be equal within a pool; it is prefilled from the
library's current pool. Step 2 previews barcode clashes per
pool (no rejection) and completes:

- the prep's existing pools are deleted; a new pool keeps the old pool's experiment when
  all of its libraries came from pools of one experiment;
- one pool value → one pool named ``<prep>``; several → ``<prep>_<value>``;
- ``x`` marks the library FAILED, ``skip``/``t`` leave it untouched;
- pooled libraries become POOLED;
- each new pool gets the M reads requested of its rows.

FastAPI also moves an ACCEPTED request to PREPARED once all its libraries are pooled
(legacy collected the request IDs into a set that was never filled).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_experiment, create_lab_prep, create_library, create_seq_request
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
    spreadsheet_payload,
)

COLUMNS = ["Library", "Pool", "M Reads Requested"]


def _url(client: TestClient, route: str) -> str:
    return client.app.url_path_for(f"LibraryPoolingWorkflow.{route}")  # type: ignore[attr-defined]


DEFAULT_NUM_M_READS = 100.0


def _payload(rows: list[tuple]) -> dict[str, str]:
    """Rows are (library, pool) or (library, pool, num_m_reads_requested)."""
    return spreadsheet_payload(COLUMNS, [
        [_label(row[0]), row[1], row[2] if len(row) > 2 else DEFAULT_NUM_M_READS] for row in rows
    ])


def _label(library: models.Library) -> str:
    """The library's option in the Library column."""
    return f"{library.name} [{library.id}]"


class Prep:
    """A lab prep with three indexed libraries (A, B, C) of one ACCEPTED request."""

    def __init__(self, session: SyncSession, insider: models.User, user: models.User):
        self.lab_prep = create_lab_prep(session, insider)
        self.seq_request = create_seq_request(session, user)
        self.seq_request.status = C.SeqRequestStatus.ACCEPTED
        session.save(self.seq_request, flush=True)
        self.libraries: list[models.Library] = []
        for i, sequence in enumerate(["ACGTACGT", "TTGGCCAA", "GATCGATC"]):
            library = create_library(session, user, self.seq_request)
            library.lab_prep_id = self.lab_prep.id
            library.status = C.LibraryStatus.PREPARING
            library.indices.append(models.LibraryIndex(name_i7=f"IDX{i}", sequence_i7=sequence))
            session.save(library, flush=True)
            self.libraries.append(library)
        session.commit()
        self.params = {"lab_prep_id": self.lab_prep.id, "uuid": str(uuid.uuid4())}

    @property
    def a(self) -> models.Library:
        return self.libraries[0]

    @property
    def b(self) -> models.Library:
        return self.libraries[1]

    @property
    def c(self) -> models.Library:
        return self.libraries[2]


@pytest.fixture
def prep(session: SyncSession, insider, user) -> Prep:
    return Prep(session, insider, user)


def _select(client: TestClient, prep: Prep, token: str, rows: list[tuple]):
    return post_form(client, _url(client, "LibraryPoolingForm.Submit"), _payload(rows), token=token, params=prep.params)


def _complete(client: TestClient, prep: Prep, token: str):
    return post_form(client, _url(client, "CompleteLibraryPoolingForm.Submit"), {}, token=token, params=prep.params)


def _run(client: TestClient, prep: Prep, token: str, rows: list[tuple]):
    response = _select(client, prep, token, rows)
    assert response.status_code == 200, response.text
    return _complete(client, prep, token)


def _pools(session: SyncSession, prep: Prep) -> dict[str, list[int]]:
    """Pool name → sorted library IDs, for the prep's pools."""
    session.expire_all()
    lab_prep = session.get_one(Q.lab_prep.select(id=prep.lab_prep.id))
    return {pool.name: sorted(library.id for library in pool.libraries) for pool in lab_prep.pools}


def _library(session: SyncSession, library: models.Library) -> models.Library:
    session.expire_all()
    return session.get_one(Q.library.select(id=library.id))


# ── Begin ───────────────────────────────────────────────────────────────────


def test_begin_lists_prep_libraries(client: TestClient, session: SyncSession, prep: Prep, user, insider_token: str):
    outside = create_library(session, user, prep.seq_request)
    session.commit()

    response = get(client, _url(client, "Begin"), insider_token, params=prep.params)

    assert response.status_code == 200, response.text
    for library in prep.libraries:
        assert library.name in response.text
    assert outside.name not in response.text


def test_client_is_denied(client: TestClient, session: SyncSession, prep: Prep, user_token: str):
    assert get(client, _url(client, "Begin"), user_token, params=prep.params).status_code == 403
    assert _select(client, prep, user_token, [(lib, "1") for lib in prep.libraries]).status_code == 403
    assert _complete(client, prep, user_token).status_code == 403
    assert _pools(session, prep) == {}


def test_anonymous_is_redirected_to_login(client: TestClient, prep: Prep):
    response = get(client, _url(client, "Begin"), params=prep.params)
    assert response.status_code == 303
    assert "/auth/login" in response.headers.get("location", "")


def test_unknown_lab_prep_is_404(client: TestClient, insider_token: str):
    assert get(client, _url(client, "Begin"), insider_token, params={"lab_prep_id": 999999}).status_code == 404


def test_csrf_mismatch_is_rejected(client: TestClient, prep: Prep, insider_token: str):
    response = post_form_csrf_mismatch(
        client, _url(client, "LibraryPoolingForm.Submit"), _payload([(lib, "1") for lib in prep.libraries]),
        token=insider_token, params=prep.params,
    )
    assert response.status_code not in (200, 204)


# ── Step 1: pool assignment ─────────────────────────────────────────────────


def test_valid_assignment_shows_barcode_preview_per_pool(client: TestClient, prep: Prep, insider_token: str):
    response = _select(client, prep, insider_token, [(prep.a, "1"), (prep.b, "1"), (prep.c, "2")])

    assert response.status_code == 200, response.text
    for library in prep.libraries:
        assert library.name in response.text
    assert "cemm-red" not in response.text


def test_barcode_clash_is_shown_but_not_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    """Legacy only previewed clashes; completion still pools the libraries."""
    prep.b.indices[0].sequence_i7 = prep.a.indices[0].sequence_i7
    session.save(prep.b, flush=True)
    session.commit()

    response = _select(client, prep, insider_token, [(prep.a, "1"), (prep.b, "1"), (prep.c, "1")])

    assert response.status_code == 200, response.text
    assert "cemm-red" in response.text
    assert_htmx_redirect(_complete(client, prep, insider_token), f"/lab_preps/{prep.lab_prep.id}")


def test_clash_across_pools_is_not_an_error(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    prep.b.indices[0].sequence_i7 = prep.a.indices[0].sequence_i7
    session.save(prep.b, flush=True)
    session.commit()

    response = _select(client, prep, insider_token, [(prep.a, "1"), (prep.b, "2"), (prep.c, "1")])

    assert response.status_code == 200, response.text
    assert "cemm-red" not in response.text


def test_library_name_mismatch_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    payload = spreadsheet_payload(COLUMNS, [
        [f"{prep.b.name} [{prep.a.id}]", "1", 1.0], [_label(prep.b), "1", 1.0], [_label(prep.c), "1", 1.0],
    ])
    response = post_form(client, _url(client, "LibraryPoolingForm.Submit"), payload, token=insider_token, params=prep.params)

    assert_form_invalid(response, "for 'Library'")


def test_library_outside_prep_is_rejected(client: TestClient, session: SyncSession, prep: Prep, user, insider_token: str):
    outside = create_library(session, user, prep.seq_request)
    session.commit()

    response = _select(client, prep, insider_token, [(prep.a, "1"), (prep.b, "1"), (outside, "1")])

    assert_form_invalid(response, "for 'Library'")


def test_library_marked_as_control_is_rejected(client: TestClient, prep: Prep, insider_token: str):
    response = _select(client, prep, insider_token, [(prep.a, "t"), (prep.b, "1"), (prep.c, "1")])

    assert_form_invalid(response, "Requested library cannot be marked as control")


def test_missing_pool_is_rejected(client: TestClient, prep: Prep, insider_token: str):
    response = _select(client, prep, insider_token, [(prep.a, ""), (prep.b, "1"), (prep.c, "1")])

    assert_form_invalid(response)


def test_missing_num_m_reads_is_rejected(client: TestClient, prep: Prep, insider_token: str):
    response = _select(client, prep, insider_token, [(prep.a, "1", None), (prep.b, "1"), (prep.c, "1")])

    assert_form_invalid(response, "Number of M reads requested is required")


def test_negative_num_m_reads_is_rejected(client: TestClient, prep: Prep, insider_token: str):
    response = _select(client, prep, insider_token, [(prep.a, "1", -1), (prep.b, "1", -1), (prep.c, "1", -1)])

    assert_form_invalid(response, "Number of M reads requested must be >= 0")


def test_different_num_m_reads_within_pool_is_rejected(client: TestClient, prep: Prep, insider_token: str):
    response = _select(client, prep, insider_token, [(prep.a, "1", 10), (prep.b, "1", 20), (prep.c, "2", 30)])

    assert_form_invalid(response, "All libraries in pool '1' must have the same number of M reads requested")


def test_num_m_reads_not_required_for_x_and_skip(client: TestClient, prep: Prep, insider_token: str):
    response = _select(client, prep, insider_token, [(prep.a, "1"), (prep.b, "x", None), (prep.c, "skip", None)])

    assert response.status_code == 200, response.text


# ── Completion ──────────────────────────────────────────────────────────────


def test_several_pools_are_created_with_suffix(
    client: TestClient, session: SyncSession, prep: Prep, insider, insider_token: str,
):
    response = _run(client, prep, insider_token, [(prep.a, "1"), (prep.b, "1"), (prep.c, "2")])

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert_flash(response, "Library pooling completed!", category="success")
    name = prep.lab_prep.name
    assert _pools(session, prep) == {f"{name}_1": sorted([prep.a.id, prep.b.id]), f"{name}_2": [prep.c.id]}
    for library in prep.libraries:
        assert _library(session, library).status == C.LibraryStatus.POOLED

    pool = session.get_one(Q.pool.select(id=_library(session, prep.c).pool_id))
    assert (pool.type, pool.owner_id, pool.contact.email, pool.contact.name) == (
        C.PoolType.INTERNAL, insider.id, insider.email, insider.name,
    )


def test_pools_get_num_m_reads_requested(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    _run(client, prep, insider_token, [(prep.a, "1", 0), (prep.b, "1", 0), (prep.c, "2", 250.5)])

    session.expire_all()
    pool_1 = session.get_one(Q.pool.select(id=_library(session, prep.a).pool_id))
    pool_2 = session.get_one(Q.pool.select(id=_library(session, prep.c).pool_id))
    assert (pool_1.num_m_reads_requested, pool_2.num_m_reads_requested) == (0.0, 250.5)


def test_single_pool_gets_num_m_reads_requested(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    _run(client, prep, insider_token, [(lib, "A", 42) for lib in prep.libraries])

    session.expire_all()
    pool = session.get_one(Q.pool.select(id=_library(session, prep.a).pool_id))
    assert pool.num_m_reads_requested == 42.0


def test_begin_prefills_num_m_reads_from_current_pool(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    _run(client, prep, insider_token, [(prep.a, "1", 123.5), (prep.b, "1", 123.5), (prep.c, "skip", None)])

    prep.params["uuid"] = str(uuid.uuid4())
    response = get(client, _url(client, "Begin"), insider_token, params=prep.params)

    assert response.status_code == 200, response.text
    assert "123.5" in response.text


def test_single_pool_is_named_after_prep(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    response = _run(client, prep, insider_token, [(prep.a, "A"), (prep.b, "A"), (prep.c, "A")])

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert _pools(session, prep) == {prep.lab_prep.name: sorted(lib.id for lib in prep.libraries)}


def test_prep_name_prefix_is_not_doubled(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    name = prep.lab_prep.name
    _run(client, prep, insider_token, [(prep.a, f"{name}_1"), (prep.b, f"{name}_1"), (prep.c, "2")])

    assert sorted(_pools(session, prep)) == [f"{name}_1", f"{name}_2"]


def test_x_marks_library_failed(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    _run(client, prep, insider_token, [(prep.a, "1"), (prep.b, "1"), (prep.c, "x")])

    assert _pools(session, prep) == {f"{prep.lab_prep.name}_1": sorted([prep.a.id, prep.b.id])}
    c = _library(session, prep.c)
    assert (c.status, c.pool_id) == (C.LibraryStatus.FAILED, None)


def test_all_libraries_x_creates_no_pool(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    """With a single pool value the rows are pooled as '1' — but 'x' must still mean failed."""
    response = _run(client, prep, insider_token, [(lib, "x") for lib in prep.libraries])

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert _pools(session, prep) == {}
    for library in prep.libraries:
        assert _library(session, library).status == C.LibraryStatus.FAILED


def test_skip_leaves_library_untouched(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    _run(client, prep, insider_token, [(prep.a, "1"), (prep.b, "1"), (prep.c, "skip")])

    c = _library(session, prep.c)
    assert (c.status, c.pool_id) == (C.LibraryStatus.PREPARING, None)


def test_rerun_replaces_pools(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    _run(client, prep, insider_token, [(prep.a, "1"), (prep.b, "1"), (prep.c, "2")])
    old_ids = [lib.pool_id for lib in (_library(session, prep.a), _library(session, prep.c))]

    prep.params["uuid"] = str(uuid.uuid4())
    _run(client, prep, insider_token, [(prep.a, "1"), (prep.b, "2"), (prep.c, "2")])

    name = prep.lab_prep.name
    assert _pools(session, prep) == {f"{name}_1": [prep.a.id], f"{name}_2": sorted([prep.b.id, prep.c.id])}
    for pool_id in old_ids:
        assert session.first(Q.pool.select(id=pool_id)) is None


def test_rerun_keeps_experiment_of_unchanged_pool(
    client: TestClient, session: SyncSession, prep: Prep, insider, insider_token: str,
):
    _run(client, prep, insider_token, [(prep.a, "1"), (prep.b, "1"), (prep.c, "2")])
    experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP)
    pool_1 = session.get_one(Q.pool.select(id=_library(session, prep.a).pool_id))
    pool_1.experiment_id = experiment.id
    session.save(pool_1, flush=True)
    session.commit()

    prep.params["uuid"] = str(uuid.uuid4())
    _run(client, prep, insider_token, [(prep.a, "1"), (prep.b, "1"), (prep.c, "2")])

    session.expire_all()
    new_1 = session.get_one(Q.pool.select(id=_library(session, prep.a).pool_id))
    new_2 = session.get_one(Q.pool.select(id=_library(session, prep.c).pool_id))
    assert (new_1.experiment_id, new_2.experiment_id) == (experiment.id, None)


def test_request_becomes_prepared_when_all_libraries_pooled(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    _run(client, prep, insider_token, [(lib, "1") for lib in prep.libraries])

    session.expire_all()
    assert session.get_one(Q.seq_request.select(id=prep.seq_request.id)).status == C.SeqRequestStatus.PREPARED


def test_request_stays_accepted_while_a_library_is_unpooled(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    _run(client, prep, insider_token, [(prep.a, "1"), (prep.b, "1"), (prep.c, "skip")])

    session.expire_all()
    assert session.get_one(Q.seq_request.select(id=prep.seq_request.id)).status == C.SeqRequestStatus.ACCEPTED


# ── Navigation and state ────────────────────────────────────────────────────


def test_back_navigation_keeps_assignment(client: TestClient, prep: Prep, insider_token: str):
    _select(client, prep, insider_token, [(prep.a, "P1"), (prep.b, "P2"), (prep.c, "P3")])

    response = get(client, _url(client, "LibraryPoolingForm.Previous"), insider_token, params=prep.params)

    assert response.status_code == 200, response.text
    for pool in ("P1", "P2", "P3"):
        assert pool in response.text


def test_completion_clears_workflow_state(client: TestClient, prep: Prep, insider_token: str):
    _run(client, prep, insider_token, [(lib, "1") for lib in prep.libraries])

    r = Redis(connection_pool=client.app.state.redis_pool)  # type: ignore[attr-defined]
    assert list(r.scan_iter(f"LibraryPoolingWorkflow:{prep.params['uuid']}:*")) == []


def test_replayed_completion_is_controlled(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    """After completion the state is gone: a second POST must not 500 or create pools again."""
    _run(client, prep, insider_token, [(lib, "1") for lib in prep.libraries])
    pools_before = _pools(session, prep)

    response = _complete(client, prep, insider_token)

    assert response.status_code == 400
    assert _pools(session, prep) == pools_before


def test_complete_without_assignment_is_controlled(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    response = _complete(client, prep, insider_token)

    assert response.status_code == 400
    assert _pools(session, prep) == {}
