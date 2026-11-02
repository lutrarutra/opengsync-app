"""LibraryAnnotationWorkflow 'Specify Library Protocols': an optional protocol per library for pooled and unpooled
libraries (raw samples skip it, the facility chooses the protocol), saved as ``library.protocol_id`` on completion.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_protocol, create_seq_request
from ._workflow import (
    AnnotationWorkflow, BARCODE_COLUMNS, HUMAN, libraries_by_name, pool_mapping, spreadsheet, spreadsheet_records,
)
from server.core import redis
from server.forms.workflows.library_annotation import LibraryAnnotationWorkflow, LibraryProtocolAnnotationForm

L = C.LibraryType
STEP = "library-protocol-annotation"
COLUMNS = ["Library", "Protocol"]


def _pooled_at_protocols(client, session: SyncSession, user, token: str, samples: tuple[str, ...] = ("PR_1", "PR_2")):
    """Pooled bulk RNA-seq libraries up to the protocol step; returns (wf, seq_request, library names)."""
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()
    wf = AnnotationWorkflow(client, token, seq_request.id)
    wf.begin()
    wf.project("Protocol annotation")
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(list(samples))
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="pooled-library-annotation")
    libs = [f"{s}_{L.BULK_RNA_SEQ.identifier}" for s in samples]
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[lib, "PR_Pool"] for lib in libs]), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["PR_Pool"]), next_step="barcode-input")
    sequences = ["ACGTACGTAA", "TTGGCCAATG", "GGTTCCAACA"]
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [lib, "", "", "", sequences[n], "", "", ""] for n, lib in enumerate(libs)
    ]), next_step="barcode-match")
    wf.post("barcode-match", {"i7_kit": "0", "i7_option": "forward", "i7_primer": "AATGATACGGCGACCACCGA"}, next_step=STEP)
    return wf, seq_request, libs


def _protocol(session: SyncSession, name: str | None = None):
    protocol = create_protocol(session)
    if name is not None:
        protocol.name = f"{name} {protocol.name[:8]}"
        session.save(protocol, flush=True)
    session.commit()
    return protocol


def _shown_protocols(response) -> dict[str, object]:
    return {record["Library"]: record["Protocol"] for record in spreadsheet_records(response)}


def _assert_rejected(response) -> None:
    assert 400 <= response.status_code < 500, f"expected a 4xx, got {response.status_code}"


# ── Applicability ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("submission_type", C.SubmissionType.as_list(), ids=lambda t: t.name)
def test_step_applies_to_library_submissions_only(submission_type: C.SubmissionType):
    workflow = SimpleNamespace(header={"submission_type_id": submission_type.id})
    expected = submission_type in (C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES)
    assert LibraryProtocolAnnotationForm.is_applicable(workflow) is expected  # type: ignore[arg-type]


def test_step_has_a_label_for_unfinished_runs():
    assert LibraryAnnotationWorkflow.STEP_LABELS["LibraryProtocolAnnotationForm"] == "Specify Library Protocols"


# ── Pooled libraries ────────────────────────────────────────────────────────

def test_step_lists_the_libraries_without_protocols(client, session: SyncSession, user, user_token):
    wf, _, libs = _pooled_at_protocols(client, session, user, user_token)
    shown = _shown_protocols(wf.last_response)
    assert list(shown) == libs
    assert all(protocol in (None, "") for protocol in shown.values())


def test_protocols_are_saved_and_optional(client, session: SyncSession, user, user_token):
    protocol = _protocol(session, "Protocol PR")
    wf, seq_request, libs = _pooled_at_protocols(client, session, user, user_token)

    review = wf.protocols({libs[0]: protocol.name})
    assert protocol.name in review.text  # Libraries table of the review
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)
    assert libraries[libs[0]].protocol_id == protocol.id
    assert libraries[libs[1]].protocol_id is None
    wf.assert_cleaned_up()


def test_no_protocols_completes(client, session: SyncSession, user, user_token):
    wf, seq_request, libs = _pooled_at_protocols(client, session, user, user_token)
    wf.protocols()
    wf.complete()
    assert {lib: library.protocol_id for lib, library in libraries_by_name(session, seq_request.id).items()} == {lib: None for lib in libs}


def test_protocol_name_ignores_case(client, session: SyncSession, user, user_token):
    protocol = _protocol(session, "Protocol Case")
    wf, seq_request, libs = _pooled_at_protocols(client, session, user, user_token)
    wf.protocols({libs[0]: protocol.name.upper(), libs[1]: f"  {protocol.name.lower()}  "})
    wf.complete()
    libraries = libraries_by_name(session, seq_request.id)
    assert libraries[libs[0]].protocol_id == protocol.id
    assert libraries[libs[1]].protocol_id == protocol.id


def test_unknown_protocol_is_a_cell_error(client, session: SyncSession, user, user_token):
    wf, seq_request, libs = _pooled_at_protocols(client, session, user, user_token)
    response = wf.post(STEP, spreadsheet(COLUMNS, [[libs[0], "No Such Protocol"], [libs[1], ""]]), status=202)
    assert wf.rendered_step(response) == STEP
    assert session.count(Q.library.select(seq_request_id=seq_request.id)) == 0


def test_ambiguous_protocol_name_is_a_cell_error(client, session: SyncSession, user, user_token):
    protocol = _protocol(session, "Protocol Ambiguous")
    twin = create_protocol(session)
    twin.name = protocol.name.upper()
    session.save(twin, flush=True)
    session.commit()
    wf, _, libs = _pooled_at_protocols(client, session, user, user_token)
    wf.post(STEP, spreadsheet(COLUMNS, [[libs[0], protocol.name.lower()], [libs[1], ""]]), status=202)


def test_rows_not_matching_a_library_are_ignored(client, session: SyncSession, user, user_token):
    protocol = _protocol(session, "Protocol Extra")
    wf, seq_request, libs = _pooled_at_protocols(client, session, user, user_token)
    wf.post(STEP, spreadsheet(COLUMNS, [[libs[0], ""], [libs[1], ""], ["Sneaky_Library", protocol.name]]), next_step="complete-s-a-s")
    wf.complete()
    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == set(libs)
    assert all(library.protocol_id is None for library in libraries.values())


def test_back_from_review_prefills_and_resubmit_replaces(client, session: SyncSession, user, user_token):
    first = _protocol(session, "Protocol First")
    second = _protocol(session, "Protocol Second")
    wf, seq_request, libs = _pooled_at_protocols(client, session, user, user_token)
    review = wf.protocols({libs[0]: first.name})
    assert wf.back_step(review) == STEP

    wf.last_response = wf.back(STEP)
    shown = _shown_protocols(wf.last_response)
    assert shown[libs[0]] == first.id  # the QueryColumn cell holds the id, labelled by its lookup
    assert shown[libs[1]] in (None, "")

    wf.protocols({libs[1]: second.name})
    wf.complete()
    libraries = libraries_by_name(session, seq_request.id)
    assert libraries[libs[0]].protocol_id is None
    assert libraries[libs[1]].protocol_id == second.id


def test_multiple_library_types_per_sample_are_chosen_independently(client, session: SyncSession, user, user_token):
    gex = _protocol(session, "Protocol GEX")
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.UNPOOLED_LIBRARIES)
    session.commit()
    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Protocol unpooled")
    wf.samples([["PU_1", HUMAN]])
    wf.attributes(["PU_1"])
    response = wf.service(C.ServiceType.BULK_RNA_SEQ, next_step=STEP)
    libs = list(_shown_protocols(response))
    assert libs == [f"PU_1_{L.BULK_RNA_SEQ.identifier}"]
    wf.protocols({libs[0]: gex.name})
    wf.complete()
    assert libraries_by_name(session, seq_request.id)[libs[0]].protocol_id == gex.id


# ── Raw samples ─────────────────────────────────────────────────────────────

def test_raw_samples_skip_the_step(client, session: SyncSession, user, user_token):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Protocol raw")
    wf.samples([["PRaw_1", HUMAN]])
    wf.attributes(["PRaw_1"])
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="complete-s-a-s")

    protocol = _protocol(session, "Protocol Raw")
    lib = f"PRaw_1_{L.BULK_RNA_SEQ.identifier}"
    lenient = AnnotationWorkflow(TestClient(client.app, raise_server_exceptions=False), user_token, seq_request.id)
    lenient.uuid, lenient.params = wf.uuid, wf.params
    _assert_rejected(lenient.post(STEP, spreadsheet(COLUMNS, [[lib, protocol.name]]), status=None))

    wf.complete()
    assert libraries_by_name(session, seq_request.id)[lib].protocol_id is None


# ── Regressions ─────────────────────────────────────────────────────────────

def test_step_cannot_be_posted_before_it_is_reached(client, session: SyncSession, user, user_token):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()
    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Protocol early")
    wf.samples([["PE_1", HUMAN]])
    wf.attributes(["PE_1"])
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="pooled-library-annotation")
    _assert_rejected(wf.post(STEP, spreadsheet(COLUMNS, [[f"PE_1_{L.BULK_RNA_SEQ.identifier}", ""]]), status=None))


def test_deleted_protocol_is_rejected_at_completion(client, session: SyncSession, user, user_token):
    protocol = _protocol(session, "Protocol Deleted")
    wf, seq_request, libs = _pooled_at_protocols(client, session, user, user_token)
    wf.protocols({libs[0]: protocol.name})

    session.delete(protocol)
    session.commit()

    response = wf.post("complete-s-a-s", status=None)
    assert response.status_code == 400
    assert "no longer exists" in response.text
    assert session.count(Q.library.select(seq_request_id=seq_request.id)) == 0
    assert session.count(Q.pool.select(seq_request_id=seq_request.id)) == 0

    # The run is kept: go back and choose again
    wf.last_response = wf.back(STEP)
    wf.protocols()
    wf.complete()
    assert libraries_by_name(session, seq_request.id)[libs[0]].protocol_id is None


def test_run_from_before_the_step_completes_without_protocols(client, session: SyncSession, user, user_token):
    """A run stored before the step existed has no 'protocol_id' column in its library table."""
    wf, seq_request, libs = _pooled_at_protocols(client, session, user, user_token)
    wf.protocols()

    r = redis.RedisClient(pool=client.app.state.redis_pool)
    state = LibraryAnnotationWorkflow(step="CompleteSASForm", seq_request_id=seq_request.id, r=r, uuid=wf.uuid)
    state.tables["library_table"] = state.tables["library_table"].drop(columns=["protocol_id"])
    state.tables.save()

    wf.complete()
    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == set(libs)
    assert all(library.protocol_id is None for library in libraries.values())
