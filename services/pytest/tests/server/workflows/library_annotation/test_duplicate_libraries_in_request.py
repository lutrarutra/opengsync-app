"""LibraryAnnotationWorkflow: a sample cannot get a second library of the same type in one request (all service paths)."""

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, libraries_by_name, spreadsheet

L = C.LibraryType
LABEL = dict(C.LibraryType.as_selectable())


def test_duplicate_libraries_in_request(
    client, session: SyncSession, user, user_token,
):
    project = session.save(Q.project.create(title="Duplicate Library Project", description="dup", owner_id=user.id), flush=True)
    session.commit()
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    def start(samples: list[str]) -> AnnotationWorkflow:
        wf = AnnotationWorkflow(client, user_token, seq_request.id)
        wf.begin()
        wf.post("project-select", {"existing_project": str(project.id)}, next_step="sample-annotation")
        wf.samples([[s, HUMAN] for s in samples])
        wf.attributes(samples)
        return wf

    # 1st annotation: Dup_A gets 10X 3' GEX.
    wf = start(["Dup_A"])
    wf.service(C.ServiceType.TENX_SC_GEX_3PRIME, next_step="complete-s-a-s")
    wf.complete()

    # Plain service path: same sample + same library type is rejected, the request is unchanged.
    wf = start(["Dup_A", "Dup_B"])
    wf.service(C.ServiceType.TENX_SC_GEX_3PRIME, status=202)
    assert set(libraries_by_name(session, seq_request.id)) == {f"Dup_A_{L.TENX_SC_GEX_3PRIME.identifier}"}
    # A different library type for the same sample is fine.
    wf.service(C.ServiceType.TENX_SC_GEX_5PRIME, next_step="complete-s-a-s")
    wf.complete()

    # Custom path: the duplicate row is rejected, other library types are accepted.
    wf = start(["Dup_A"])
    wf.service(C.ServiceType.CUSTOM, next_step="custom-assay-annotation")
    columns = ["Sample Name (Pool)", "Library Type"]
    wf.post("custom-assay-annotation", spreadsheet(columns, [
        ["Dup_A", LABEL[L.ATAC_SEQ.id]],
        ["Dup_A", LABEL[L.TENX_SC_GEX_5PRIME.id]],
    ]), status=202)
    wf.post("custom-assay-annotation", spreadsheet(columns, [["Dup_A", LABEL[L.ATAC_SEQ.id]]]), next_step="complete-s-a-s")
    wf.complete()

    # Custom + multiplexing: checked for every sample of the pool.
    wf = start(["Dup_A", "Dup_C"])
    wf.service(C.ServiceType.CUSTOM, next_step="define-multiplexed-samples", additional_services__ocm_multiplexing="on")
    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [["Dup_A", "Dup_Pool"], ["Dup_C", "Dup_Pool"]],
    ), next_step="custom-assay-annotation")
    wf.post("custom-assay-annotation", spreadsheet(columns, [["Dup_Pool", LABEL[L.ATAC_SEQ.id]]]), status=202)  # Dup_A has ATAC-seq already
    wf.post("custom-assay-annotation", spreadsheet(columns, [["Dup_Pool", LABEL[L.WGS.id]]]), next_step="complete-s-a-s")
    wf.complete()

    session.expire_all()
    assert len(session.get_all(Q.sample.select(project_id=project.id), limit=None)) == 3  # samples are reused, not duplicated
    assert set(libraries_by_name(session, seq_request.id)) == {
        f"Dup_A_{L.TENX_SC_GEX_3PRIME.identifier}",
        f"Dup_A_{L.TENX_SC_GEX_5PRIME.identifier}",
        f"Dup_B_{L.TENX_SC_GEX_5PRIME.identifier}",
        f"Dup_A_{L.ATAC_SEQ.identifier}",
        f"Dup_Pool_{L.WGS.identifier}",
    }
