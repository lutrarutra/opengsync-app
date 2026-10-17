"""LibraryAnnotationWorkflow: pooled libraries, 10X Multiome (GEX + ATAC) indexed from index kits."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, ATAC_BARCODE_COLUMNS,
    create_dual_index_kit, create_tenx_atac_index_kit, pool_mapping,
    libraries_by_name, linked_samples, spreadsheet,
)

L = C.LibraryType

ATAC_A1 = ["AAACGGCG", "CCTACCAT", "GGCGTTTC", "TTGTAAGA"]
ATAC_A2 = ["AGCCCTTT", "CAAGTCCA", "GTGAGAAG", "TCTTAGGC"]


def test_pooled_10x_multiome_kit_indices_annotation(
    client, session: SyncSession, user, user_token,
):
    create_dual_index_kit(session, "TT-SET-A", "Dual Index Kit TT Set A", {
        "A1": ("SI-TT-A1", "GTAACATGCG", "SI-TT-A1", "AGGTAACACT"),
        "A2": ("SI-TT-A2", "GTGGATCAAA", "SI-TT-A2", "CAGGGTTGGC"),
    })
    create_tenx_atac_index_kit(session, "NA-SET-A", "Single Index Kit N Set A", {
        "A1": ("SI-NA-A1", ATAC_A1),
        "A2": ("SI-NA-A2", ATAC_A2),
    })

    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X Multiome pooled libraries")
    wf.samples([["Nuclei_1", HUMAN], ["Nuclei_2", HUMAN]])
    wf.attributes(["Nuclei_1", "Nuclei_2"])
    wf.service(C.ServiceType.TENX_SC_MULTIOME, next_step="pooled-library-annotation")

    gex = L.TENX_SC_GEX_3PRIME.identifier
    atac = L.TENX_SC_ATAC.identifier
    library_names = [f"{s}_{t}" for s in ["Nuclei_1", "Nuclei_2"] for t in [gex, atac]]
    wf.post("pooled-library-annotation", spreadsheet(
        ["Library Name", "Pool"], [[name, "Multiome_Pool"] for name in library_names],
    ), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Multiome_Pool"]), next_step="barcode-input")

    dual_kit = "[TT-SET-A] Dual Index Kit TT Set A"
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [f"Nuclei_1_{gex}", "A1", dual_kit, "", "", "", "", ""],
        [f"Nuclei_2_{gex}", "A2", dual_kit, "", "", "", "", ""],
    ]), next_step="t-e-n-x-a-t-a-c-barcode-input")  # kit indices: no barcode-match step

    atac_kit = "[NA-SET-A] Single Index Kit N Set A"
    wf.post("t-e-n-x-a-t-a-c-barcode-input", spreadsheet(ATAC_BARCODE_COLUMNS, [
        [f"Nuclei_1_{atac}", "A1", atac_kit, "", "", "", "", ""],
        [f"Nuclei_2_{atac}", "", atac_kit, "", "", "", "", ""],
    ]), status=202)  # kit without well or barcode name
    wf.post("t-e-n-x-a-t-a-c-barcode-input", spreadsheet(ATAC_BARCODE_COLUMNS, [
        [f"Nuclei_1_{atac}", "A1", atac_kit, "", "", "", "", ""],
        [f"Nuclei_2_{atac}", "", "", "", *ATAC_A2[:3], ""],
    ]), status=202)  # custom ATAC index needs all four sequences
    wf.post("t-e-n-x-a-t-a-c-barcode-input", spreadsheet(ATAC_BARCODE_COLUMNS, [
        [f"Nuclei_1_{atac}", "A1", atac_kit, "", "", "", "", ""],
        [f"Nuclei_2_{atac}", "", atac_kit, "SI-NA-A2", "", "", "", ""],
    ]), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == set(library_names)
    for name, library in libraries.items():
        assert library.pool is not None and library.pool.name == "Multiome_Pool"
        assert library.mux_type is None
        assert linked_samples(library) == {name.split(f"_{gex}")[0].split(f"_{atac}")[0]: None}

    assert libraries[f"Nuclei_1_{gex}"].index_type == C.IndexType.DUAL_INDEX
    assert [(i.name_i7, i.sequence_i7, i.sequence_i5) for i in libraries[f"Nuclei_1_{gex}"].indices] == [("SI-TT-A1", "GTAACATGCG", "AGGTAACACT")]
    assert [(i.name_i7, i.sequence_i7, i.sequence_i5) for i in libraries[f"Nuclei_2_{gex}"].indices] == [("SI-TT-A2", "GTGGATCAAA", "CAGGGTTGGC")]

    for sample, sequences, barcode_name in [("Nuclei_1", ATAC_A1, "SI-NA-A1"), ("Nuclei_2", ATAC_A2, "SI-NA-A2")]:
        library = libraries[f"{sample}_{atac}"]
        assert library.index_type == C.IndexType.TENX_ATAC_INDEX
        assert sorted(i.sequence_i7 for i in library.indices) == sorted(sequences)
        assert {i.name_i7 for i in library.indices} == {barcode_name}
        assert all(i.sequence_i5 is None for i in library.indices)
