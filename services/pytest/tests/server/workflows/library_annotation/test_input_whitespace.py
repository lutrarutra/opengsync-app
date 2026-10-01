"""LibraryAnnotationWorkflow: leading/trailing whitespace is stripped from every text input before it is stored."""

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, libraries_by_name, spreadsheet


def test_input_whitespace(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.post("project-select", {
        "new_project": "   Padded Project Title   ",
        "project_description": "\tPadded description \n",
    }, next_step="sample-annotation")
    wf.post("sample-annotation", spreadsheet(["Sample Name", "Genome"], [["  Pad_Sample  ", f" {HUMAN} "]]), next_step="sample-attribute-annotation")
    wf.post("sample-attribute-annotation", spreadsheet(
        ["Sample Name", "Sample ID", "Condition"], [["Pad_Sample", "(new)", "  treated  "]],
    ), next_step="select-service")
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="pooled-library-annotation", additional_info="  keep cold  ")

    library = f"Pad_Sample_{C.LibraryType.BULK_RNA_SEQ.identifier}"
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[f" {library} ", "  Pad_Pool  "]]), next_step="pool-mapping")
    wf.post("pool-mapping", {
        "contact_name": "  Jane Doe  ",
        "contact_email": "  jane.doe@example.com  ",
        "contact_phone": " +43 123 ",
        "pool_forms-0-raw_label": "Pad_Pool",
        "pool_forms-0-new_pool_name": "  Pad_Pool  ",
        "pool_forms-0-num_m_reads_requested": " 50 ",
    }, next_step="barcode-input")
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [[library, "", "", "  i7_custom ", " ACGTACGT ", "", "", ""]]), next_step="barcode-match")
    wf.post("barcode-match", {"i7_kit": "0", "i7_option": " forward ", "i7_primer": "  AATGATACGGCGACCACCGA  "}, next_step="complete-s-a-s")
    wf.complete()

    session.expire_all()
    project = session.first(Q.project.select(title="Padded Project Title"))
    assert project is not None
    assert project.description == "Padded description"

    samples = session.get_all(Q.sample.select(project_id=project.id), limit=None)
    assert [s.name for s in samples] == ["Pad_Sample"]
    assert {a.name: a.value for a in samples[0].attributes} == {"condition": "treated"}

    lib = libraries_by_name(session, seq_request.id)[library]
    assert lib.genome_ref == C.GenomeRef.HUMAN
    assert lib.pool is not None
    assert lib.pool.name == "Pad_Pool"
    assert lib.pool.num_m_reads_requested == 50
    assert (lib.pool.contact.name, lib.pool.contact.email, lib.pool.contact.phone) == ("Jane Doe", "jane.doe@example.com", "+43 123")
    assert [(i.name_i7, i.sequence_i7) for i in lib.indices] == [("i7_custom", "ACGTACGT")]
    assert lib.indices[0].orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED

    session.refresh(seq_request)
    comments = [c.text for c in seq_request.comments]
    assert any(c.endswith(": keep cold") for c in comments)
    assert "i7 Primer Sequence: AATGATACGGCGACCACCGA" in comments
