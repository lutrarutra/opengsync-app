"""LibraryAnnotationWorkflow: going back and re-submitting steps must not apply their effects twice."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, pool_mapping, libraries_by_name, spreadsheet,
)

L = C.LibraryType


def test_pooled_back_navigation_resubmit(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Back navigation pooled 3' + ABC")
    wf.samples([["Back_S1", HUMAN]])
    wf.attributes(["Back_S1"])

    service = dict(
        optional_assays__antibody_capture="on",
        optional_assays__antibody_capture_kit="TotalSeq-B Back",
        additional_info="Handle with care",
    )
    wf.service(C.ServiceType.TENX_SC_GEX_3PRIME, next_step="pooled-library-annotation", **service)
    wf.back("select-service")
    wf.service(C.ServiceType.TENX_SC_GEX_3PRIME, next_step="pooled-library-annotation", **service)

    gex = f"Back_S1_{L.TENX_SC_GEX_3PRIME.identifier}"
    abc = f"Back_S1_{L.TENX_ANTIBODY_CAPTURE.identifier}"
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[gex, "Back_Pool"], [abc, "Back_Pool"]]), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Back_Pool"]), next_step="barcode-input")
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [gex, "", "", "", "AAAACCCCGG", "", "", ""],
        [abc, "", "", "", "GGGGTTTTAA", "", "", ""],
    ]), next_step="barcode-match")

    match = {"i7_kit": "0", "i7_option": "rc", "i7_primer": "AATGATACGGCGACCACCGA"}
    wf.post("barcode-match", match, next_step="feature-annotation")
    wf.back("barcode-match")
    wf.post("barcode-match", match, next_step="feature-annotation")

    wf.post("feature-annotation", spreadsheet(
        ["Sample Name", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"],
        [["Back_S1", "", "", "CD3", "CTCATTGTAACTCCT", "5PNNNNNNNNNN(BC)", "R2"]],
    ), next_step="complete-s-a-s")
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)
    # 'rc' is applied once, to what was entered in barcode-input.
    assert libraries[gex].indices[0].sequence_i7 == "CCGGGGTTTT"
    assert libraries[abc].indices[0].sequence_i7 == "TTAAAACCCC"

    session.refresh(seq_request)
    comments = [c.text for c in seq_request.comments]
    for text in ["TotalSeq-B Back", "Handle with care", "AATGATACGGCGACCACCGA"]:
        assert sum(text in c for c in comments) == 1, f"comment containing {text!r} saved {sum(text in c for c in comments)} times"
