"""LibraryAnnotationWorkflow: pooled libraries, 10X Multiome (GEX + ATAC) with custom (non-kit) index sequences.

Index steps run barcode input -> 10X ATAC input -> barcode match."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, ATAC_BARCODE_COLUMNS, pool_mapping,
    libraries_by_name, spreadsheet, spreadsheet_rows,
)

L = C.LibraryType


def test_pooled_10x_multiome_custom_indices_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X Multiome custom indices pooled")
    wf.samples([["Nuclei_1", HUMAN]])
    wf.attributes(["Nuclei_1"])
    wf.service(C.ServiceType.TENX_SC_MULTIOME, next_step="pooled-library-annotation")

    gex = f"Nuclei_1_{L.TENX_SC_GEX_3PRIME.identifier}"
    atac = f"Nuclei_1_{L.TENX_SC_ATAC.identifier}"
    wf.post("pooled-library-annotation", spreadsheet(
        ["Library Name", "Pool"], [[gex, "Multiome_Pool"], [atac, "Multiome_Pool"]],
    ), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Multiome_Pool"]), next_step="barcode-input")
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [gex, "", "", "", "ACGTACGTAC", "", "", "TGCATGCATG"],
    ]), next_step="t-e-n-x-a-t-a-c-barcode-input")  # ATAC indices come before barcode matching

    atac_seqs = ["AAACGGCG", "CCTACCAT", "GGCGTTTC", "TTGTAAGA"]
    wf.post("t-e-n-x-a-t-a-c-barcode-input", spreadsheet(ATAC_BARCODE_COLUMNS, [
        [atac, "", "", "", "AAACGGCG", "CCTACCAT", "GGCGTTQC", "TTGTAAGA"],
    ]), status=202)  # invalid base in sequence 3
    wf.post("t-e-n-x-a-t-a-c-barcode-input", spreadsheet(ATAC_BARCODE_COLUMNS, [
        [atac, "", "", "", "aaacggcg", " CCTACCAT", "GGCG TTTC", "TTGTAAGA"],
    ]), next_step="barcode-match")  # normalised to upper case without whitespace
    # Back shows the cleaned-up sequences; re-submitting must not duplicate the ATAC indices.
    back = wf.back("t-e-n-x-a-t-a-c-barcode-input")
    assert spreadsheet_rows(back)[0][4:8] == atac_seqs
    wf.post("t-e-n-x-a-t-a-c-barcode-input", spreadsheet(ATAC_BARCODE_COLUMNS, [
        [atac, "", "", "", *atac_seqs],
    ]), next_step="barcode-match")

    # 'rc' applies to the GEX library's custom indices only, never to the ATAC indices.
    wf.post("barcode-match", {
        "i7_kit": "0", "i7_option": "rc", "i7_primer": "AATGATACGGCGACCACCGA",
        "i5_kit": "0", "i5_option": "forward", "i5_primer": "CAAGCAGAAGACGGCATACGA",
    }, next_step="complete-s-a-s")
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)
    assert libraries[gex].index_type == C.IndexType.DUAL_INDEX
    assert [(i.sequence_i7, i.sequence_i5) for i in libraries[gex].indices] == [("GTACGTACGT", "TGCATGCATG")]
    assert libraries[gex].indices[0].orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED

    assert libraries[atac].index_type == C.IndexType.TENX_ATAC_INDEX
    assert sorted(i.sequence_i7 for i in libraries[atac].indices) == sorted(atac_seqs)
    assert all(i.sequence_i5 is None for i in libraries[atac].indices)
