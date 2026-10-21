"""LibraryAnnotationWorkflow: pooled libraries, custom service with 10X Flex GEX + Flex ABC (and another type) on one sample.

Regression: the Flex step rebuilt the library table from the 'antibody capture' service flag, which a custom
service never sets, so every custom library except Flex GEX was dropped. The probe barcodes are stored on the
Flex libraries only (as TENX_FLEX_PROBE), samples without a Flex library get no probe barcode row, and a blank
barcode (only allowed for a custom service) means the Flex library is single-plex.
"""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, pool_mapping,
    libraries_by_name, linked_samples, spreadsheet, spreadsheet_rows,
)

L = C.LibraryType
LABEL = dict(C.LibraryType.as_selectable())


def test_pooled_custom_flex_abc_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Custom Flex GEX + ABC pooled libraries")
    wf.samples([["sample_1", HUMAN], ["sample_2", HUMAN], ["sample_3", HUMAN]])
    wf.attributes(["sample_1", "sample_2", "sample_3"])
    wf.service(C.ServiceType.CUSTOM, next_step="custom-assay-annotation")

    flex_step = wf.post("custom-assay-annotation", spreadsheet(["Sample Name (Pool)", "Library Type"], [
        ["sample_1", LABEL[L.TENX_SC_GEX_FLEX.id]],
        ["sample_1", LABEL[L.TENX_SC_ABC_FLEX.id]],
        ["sample_1", LABEL[L.BULK_RNA_SEQ.id]],
        ["sample_2", LABEL[L.TENX_SC_GEX_FLEX.id]],
        ["sample_3", LABEL[L.BULK_RNA_SEQ.id]],
    ]), next_step="flex-annotation")
    assert [row[:2] for row in spreadsheet_rows(flex_step)] == [["sample_1", "sample_1"], ["sample_2", "sample_2"]]

    pooled_step = wf.post("flex-annotation", spreadsheet(["Sample Name", "Multiplexing Pool", "Barcode ID"], [
        ["sample_1", "sample_1", "BC001"], ["sample_2", "sample_2", ""],  # single-plex
    ]), next_step="pooled-library-annotation")

    gex_1 = f"sample_1_{L.TENX_SC_GEX_FLEX.identifier}"
    abc_1 = f"sample_1_{L.TENX_SC_ABC_FLEX.identifier}"
    bulk_1 = f"sample_1_{L.BULK_RNA_SEQ.identifier}"
    gex_2 = f"sample_2_{L.TENX_SC_GEX_FLEX.identifier}"
    bulk_3 = f"sample_3_{L.BULK_RNA_SEQ.identifier}"
    libraries = [gex_1, abc_1, bulk_1, gex_2, bulk_3]
    assert [row[0] for row in spreadsheet_rows(pooled_step)] == libraries

    wf.post("pooled-library-annotation", spreadsheet(
        ["Library Name", "Pool"], [[name, "Custom_Flex_Pool"] for name in libraries],
    ), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Custom_Flex_Pool"]), next_step="barcode-input")
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [gex_1, "", "", "", "ACGTACGTAC", "", "", ""],
        [abc_1, "", "", "", "TTGGCCAATT", "", "", ""],
        [bulk_1, "", "", "", "GGCCTTAAGG", "", "", ""],
        [gex_2, "", "", "", "CATGCATGCA", "", "", ""],
        [bulk_3, "", "", "", "AACCGGTTAA", "", "", ""],
    ]), next_step="barcode-match")
    wf.post("barcode-match", {"i7_kit": "0", "i7_option": "forward", "i7_primer": "AATGATACGGCGACCACCGA"}, next_step="feature-annotation")
    wf.post("feature-annotation", spreadsheet(
        ["Sample", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"],
        [["sample_1 [new]", "", "", "CD3", "CTCATTGTAACTCCT", "5PNNNNNNNNNN(BC)", "R2"]],
    ), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    created = libraries_by_name(session, seq_request.id)
    assert {name: library.type for name, library in created.items()} == {
        gex_1: L.TENX_SC_GEX_FLEX, abc_1: L.TENX_SC_ABC_FLEX, bulk_1: L.BULK_RNA_SEQ,
        gex_2: L.TENX_SC_GEX_FLEX, bulk_3: L.BULK_RNA_SEQ,
    }
    for library in created.values():
        assert library.service_type == C.ServiceType.CUSTOM
        assert library.pool is not None and library.pool.name == "Custom_Flex_Pool"

    # Multiplexed Flex libraries carry the probe barcodes (ABC as 'AB'); single-plex Flex and other libraries do not
    assert {name: library.mux_type for name, library in created.items()} == {
        gex_1: C.MUXType.TENX_FLEX_PROBE, abc_1: C.MUXType.TENX_FLEX_PROBE, bulk_1: None,
        gex_2: None, bulk_3: None,
    }
    assert linked_samples(created[gex_1]) == {"sample_1": {"barcode": "BC001"}}
    assert linked_samples(created[abc_1]) == {"sample_1": {"barcode": "AB001"}}
    assert linked_samples(created[gex_2]) == {"sample_2": None}
    assert linked_samples(created[bulk_1]) == {"sample_1": None}
    assert linked_samples(created[bulk_3]) == {"sample_3": None}
    assert [f.name for f in created[abc_1].features] == ["CD3"]
