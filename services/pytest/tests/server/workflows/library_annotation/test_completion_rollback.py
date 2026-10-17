"""LibraryAnnotationWorkflow: a failure during completion leaves nothing behind.

Completion creates the project, samples, pools, libraries and indices in one request; the
session middleware commits only on a 2xx response. A failure after most records are
flushed (here: linking samples to libraries) must roll all of them back and keep the
workflow state, so the same run can be completed once the problem is gone.
"""

import opengsync_db
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, pool_mapping, libraries_by_name, spreadsheet,
)

L = C.LibraryType
TITLE = "Rollback project"


def _pooled_at_review(client, session: SyncSession, user, token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()
    wf = AnnotationWorkflow(client, token, seq_request.id)
    wf.begin()
    wf.project(TITLE)
    samples = ["Roll_1", "Roll_2"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="pooled-library-annotation")
    libs = [f"{s}_{L.BULK_RNA_SEQ.identifier}" for s in samples]
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[lib, "Roll_Pool"] for lib in libs]), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Roll_Pool"]), next_step="barcode-input")
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [libs[0], "", "", "", "ACGTACGTAC", "", "", ""],
        [libs[1], "", "", "", "TGCATGCATG", "", "", ""],
    ]), next_step="barcode-match")
    wf.post("barcode-match", {"i7_kit": "0", "i7_option": "forward", "i7_primer": "AATGATACGGCGACCACCGA"}, next_step="complete-s-a-s")
    return seq_request, wf, libs


def test_failure_during_completion_rolls_back_everything(client, session: SyncSession, user, user_token, monkeypatch):
    seq_request, wf, libs = _pooled_at_review(client, session, user, user_token)

    def fail(*args, **kwargs):
        raise RuntimeError("link failed")

    monkeypatch.setattr(opengsync_db.actions, "link_sample_library", fail)
    lenient = AnnotationWorkflow(TestClient(client.app, raise_server_exceptions=False), user_token, seq_request.id)
    lenient.uuid, lenient.params = wf.uuid, wf.params
    response = lenient.post("complete-s-a-s", status=None)

    assert response.status_code == 500
    session.expire_all()
    assert session.first(Q.project.select(title=TITLE)) is None
    assert session.count(Q.library.select(seq_request_id=seq_request.id)) == 0
    assert session.count(Q.pool.select(seq_request_id=seq_request.id)) == 0
    assert session.count(Q.sample.select(name="Roll_1")) == 0
    session.refresh(seq_request)
    assert seq_request.comments == []
    # The workflow state survives, so the user can retry.
    assert Redis(connection_pool=client.app.state.redis_pool).keys(f"LibraryAnnotationWorkflow:{wf.uuid}:*") != []

    monkeypatch.undo()
    wf.complete()
    wf.assert_cleaned_up()
    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == set(libs)
    assert session.count(Q.pool.select(seq_request_id=seq_request.id)) == 1
    session.expire_all()
    assert session.first(Q.project.select(title=TITLE)) is not None
