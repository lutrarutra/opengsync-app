"""LibraryAnnotationWorkflow: every step requires WRITE access to the sequencing request, not only 'begin'."""

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, spreadsheet


def test_annotation_steps_require_write_access(
    client, session: SyncSession, user, user_token, user_2_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    # Stranger: no access at all.
    stranger = AnnotationWorkflow(client, user_2_token, seq_request.id)
    stranger.post("project-select", {"new_project": "Stranger Project", "project_description": "x"}, status=403)

    # Owner fills in a few steps while the request is still a draft...
    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Submitted request project")
    wf.samples([["Late_Sample", HUMAN]])

    # ...then the request is submitted: the owner keeps READ access only.
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.save(seq_request)
    session.commit()
    from redis import Redis
    Redis(connection_pool=client.app.state.redis_pool).delete(f"access:seq_request:{seq_request.id}:user:{seq_request.requestor_id}")

    wf.post("sample-attribute-annotation", spreadsheet(["Sample Name", "Sample ID"], [["Late_Sample", "(new)"]]), status=403)
    wf.post("select-service", {"service_type": str(C.ServiceType.BULK_RNA_SEQ.id)}, status=403)
    wf.post("complete-s-a-s", status=403)

    session.expire_all()
    assert session.count(Q.library.select(seq_request_id=seq_request.id)) == 0
