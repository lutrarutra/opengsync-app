"""ReseqAction: clone selected libraries of a request or lab prep for re-sequencing.

As legacy ``reseq_workflow``: insider-only, started from a sequencing request (needs WRITE)
or a lab prep. Each selected library is cloned (``clone_number + 1``, linked to the original)
with its samples and features; "Indexed" also copies its indices, "Raw" does not. Clones stay
in the library's request. Redirects to the request / lab prep page.

Differs from legacy, kept (decided 2026-10-14): an indexed clone gets status STORED (legacy: ACCEPTED for
both types); QC-only requests cannot be re-sequenced.
"""

import json
import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C, actions

from ...db.create_units import create_lab_prep, create_library, create_project, create_sample, create_seq_request
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form

INDEXED, RAW = "0", "1"


def _url(client: TestClient, route: str) -> str:
    return client.app.url_path_for(f"ReseqAction.{route}")  # type: ignore[attr-defined]


def _library(session: SyncSession, user: models.User, seq_request: models.SeqRequest, sample: models.Sample) -> models.Library:
    library = create_library(session, user, seq_request)
    actions.link_sample_library(session, sample_id=sample.id, library_id=library.id)
    actions.add_index_to_library(
        session, library_id=library.id,
        index_kit_i7_id=None, name_i7="i7", sequence_i7="ACGTACGT",
        index_kit_i5_id=None, name_i5="i5", sequence_i5="TTGGCCAA",
        orientation=None,
    )
    return library


class Setup:
    def __init__(self, session: SyncSession, user: models.User):
        self.session = session
        self.seq_request = create_seq_request(session, user)
        self.sample = create_sample(session, user, create_project(session, user))
        self.a = _library(session, user, self.seq_request, self.sample)
        self.b = _library(session, user, self.seq_request, self.sample)
        session.commit()

    def clones(self, library: models.Library) -> list[models.Library]:
        self.session.expire_all()
        return self.session.get_all(Q.library.select().where(models.Library.original_library_id == library.id), limit=None)


@pytest.fixture
def setup(session: SyncSession, user) -> Setup:
    return Setup(session, user)


def _submit(client: TestClient, token: str, library_ids: list[int], reprep_type: str = INDEXED, **params):
    return post_form(
        client, _url(client, "Submit"),
        {"selected_library_ids": json.dumps(library_ids), "reprep_type": reprep_type},
        token=token, params=params,
    )


# ── Render ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("context", ["seq_request_id", "lab_prep_id"])
def test_render_browses_only_the_context(client: TestClient, session: SyncSession, setup: Setup, insider, insider_token: str, context: str):
    lab_prep = create_lab_prep(session, insider)
    session.commit()
    context_id = setup.seq_request.id if context == "seq_request_id" else lab_prep.id

    response = get(client, _url(client, "Begin"), insider_token, params={context: context_id})

    assert response.status_code == 200, response.text
    assert re.search(rf"render_library_table|library-table|{context}={context_id}", unescape(response.text))
    assert f"{context}={context_id}" in unescape(response.text)


def test_without_context_is_400(client: TestClient, insider_token: str):
    assert get(client, _url(client, "Begin"), insider_token).status_code == 400


# ── Cloning ─────────────────────────────────────────────────────────────────


def test_indexed_reseq_clones_samples_and_indices(client: TestClient, setup: Setup, insider_token: str):
    response = _submit(client, insider_token, [setup.a.id], INDEXED, seq_request_id=setup.seq_request.id)

    assert_htmx_redirect(response, f"/seq_requests/{setup.seq_request.id}")
    assert_flash(response, "Libraries Cloned!", "success")
    [clone] = setup.clones(setup.a)
    assert clone.id != setup.a.id
    assert clone.clone_number == 1
    assert clone.seq_request_id == setup.seq_request.id
    assert clone.status == C.LibraryStatus.STORED
    assert [link.sample_id for link in clone.sample_links] == [setup.sample.id]
    assert [(index.sequence_i7, index.sequence_i5) for index in clone.indices] == [("ACGTACGT", "TTGGCCAA")]
    assert setup.clones(setup.b) == []


def test_raw_reseq_does_not_copy_indices(client: TestClient, setup: Setup, insider_token: str):
    response = _submit(client, insider_token, [setup.a.id], RAW, seq_request_id=setup.seq_request.id)

    assert_htmx_redirect(response, f"/seq_requests/{setup.seq_request.id}")
    [clone] = setup.clones(setup.a)
    assert clone.indices == []
    assert clone.status == C.LibraryStatus.ACCEPTED
    assert [link.sample_id for link in clone.sample_links] == [setup.sample.id]


def test_multiple_libraries_get_one_clone_each(client: TestClient, setup: Setup, insider_token: str):
    _submit(client, insider_token, [setup.a.id, setup.b.id], seq_request_id=setup.seq_request.id)

    assert len(setup.clones(setup.a)) == 1
    assert len(setup.clones(setup.b)) == 1


def test_resequencing_twice_creates_two_clones(client: TestClient, setup: Setup, insider_token: str):
    """As legacy: nothing prevents re-sequencing a library again."""
    _submit(client, insider_token, [setup.a.id], seq_request_id=setup.seq_request.id)
    _submit(client, insider_token, [setup.a.id], seq_request_id=setup.seq_request.id)

    assert len(setup.clones(setup.a)) == 2


def test_cloning_a_clone_links_to_the_original(client: TestClient, setup: Setup, insider_token: str):
    _submit(client, insider_token, [setup.a.id], seq_request_id=setup.seq_request.id)
    [first] = setup.clones(setup.a)

    _submit(client, insider_token, [first.id], seq_request_id=setup.seq_request.id)

    clones = sorted(setup.clones(setup.a), key=lambda library: library.clone_number)
    assert [library.clone_number for library in clones] == [1, 2]


def test_lab_prep_context_redirects_to_the_lab_prep(client: TestClient, session: SyncSession, setup: Setup, insider, insider_token: str):
    lab_prep = create_lab_prep(session, insider)
    setup.a.lab_prep_id = lab_prep.id
    session.save(setup.a, flush=True)
    session.commit()

    response = _submit(client, insider_token, [setup.a.id], lab_prep_id=lab_prep.id)

    assert_htmx_redirect(response, f"/lab_preps/{lab_prep.id}")
    [clone] = setup.clones(setup.a)
    assert clone.seq_request_id == setup.seq_request.id  # stays in the library's request


# ── Validation and access ───────────────────────────────────────────────────


def test_empty_selection_is_rejected(client: TestClient, setup: Setup, insider_token: str):
    response = _submit(client, insider_token, [], seq_request_id=setup.seq_request.id)

    assert_form_invalid(response)


def test_library_of_another_request_is_rejected(client: TestClient, session: SyncSession, setup: Setup, user, insider_token: str):
    """The ids come from the client; a library outside the request must not be cloned into it."""
    other = Setup(session, user)

    response = _submit(client, insider_token, [setup.a.id, other.a.id], seq_request_id=setup.seq_request.id)

    assert response.status_code == 404
    assert setup.clones(setup.a) == [] and other.clones(other.a) == []


def test_library_outside_the_lab_prep_is_rejected(client: TestClient, session: SyncSession, setup: Setup, insider, insider_token: str):
    lab_prep = create_lab_prep(session, insider)
    session.commit()

    response = _submit(client, insider_token, [setup.a.id], lab_prep_id=lab_prep.id)

    assert response.status_code == 404
    assert setup.clones(setup.a) == []


def test_qc_only_request_is_rejected(client: TestClient, session: SyncSession, setup: Setup, insider_token: str):
    setup.seq_request.submission_type = C.SubmissionType.QC_ONLY
    session.save(setup.seq_request, flush=True)
    session.commit()

    assert get(client, _url(client, "Begin"), insider_token, params={"seq_request_id": setup.seq_request.id}).status_code == 400
    assert _submit(client, insider_token, [setup.a.id], seq_request_id=setup.seq_request.id).status_code == 400
    assert setup.clones(setup.a) == []


def test_request_owner_without_insider_role_is_denied(client: TestClient, setup: Setup, user_token: str):
    """As legacy: insider-only, even with WRITE on the request."""
    assert get(client, _url(client, "Begin"), user_token, params={"seq_request_id": setup.seq_request.id}).status_code == 403
    assert _submit(client, user_token, [setup.a.id], seq_request_id=setup.seq_request.id).status_code == 403
    assert setup.clones(setup.a) == []


def test_unknown_request_is_404(client: TestClient, insider_token: str):
    assert get(client, _url(client, "Begin"), insider_token, params={"seq_request_id": 999999}).status_code == 404


# ── Other clone paths (same actions.clone_library) ─────────────────────────


def _requests_named(session: SyncSession, name: str) -> list[models.SeqRequest]:
    session.expire_all()
    return session.get_all(Q.seq_request.select().where(models.SeqRequest.name == name), limit=None)


def test_single_library_reseq_from_the_request_page(client: TestClient, setup: Setup, user_token: str):
    response = post_form(client, f"/htmx/seq_requests/{setup.seq_request.id}/reseq-library/{setup.a.id}", {}, token=user_token)

    assert response.status_code == 204
    [clone] = setup.clones(setup.a)
    assert (clone.seq_request_id, clone.status, clone.clone_number) == (setup.seq_request.id, C.LibraryStatus.PREPARING, 1)
    assert len(clone.indices) == 1 and len(clone.sample_links) == 1


@pytest.mark.parametrize("method, library_status, has_indices", [
    ("pooled", C.LibraryStatus.POOLED, True),
    ("indexed", C.LibraryStatus.STORED, True),
    ("raw", C.LibraryStatus.ACCEPTED, False),
])
def test_clone_request_clones_its_libraries(
    client: TestClient, session: SyncSession, setup: Setup, user, user_token: str,
    method: str, library_status: C.LibraryStatus, has_indices: bool,
):
    from ...db.create_units import create_pool

    pool = create_pool(session, user, setup.seq_request)
    setup.a.pool_id = pool.id
    session.save(setup.a, flush=True)
    session.commit()

    response = post_form(client, f"/htmx/seq_requests/{setup.seq_request.id}/clone", {}, token=user_token, params={"method": method})

    assert response.status_code == 204, response.text
    [cloned_request] = _requests_named(session, f"RE: {setup.seq_request.name}"[:models.SeqRequest.name.type.length])
    assert cloned_request.status == C.SeqRequestStatus.DRAFT
    assert sorted(lib.original_library_id for lib in cloned_request.libraries) == sorted([setup.a.id, setup.b.id])
    assert {lib.status for lib in cloned_request.libraries} == {library_status}
    assert all(bool(lib.indices) is has_indices for lib in cloned_request.libraries)
    clone_a = next(lib for lib in cloned_request.libraries if lib.original_library_id == setup.a.id)
    if method == "pooled":
        assert clone_a.pool is not None and clone_a.pool.original_pool_id == pool.id
        assert clone_a.pool.seq_request_id == cloned_request.id
    else:
        assert clone_a.pool_id is None
