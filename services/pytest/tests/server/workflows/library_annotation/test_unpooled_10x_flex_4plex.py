"""LibraryAnnotationWorkflow: unpooled libraries, 10X Flex 4-plex with probe barcodes (no pooling/indexing steps)."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, libraries_by_name, linked_samples, spreadsheet

L = C.LibraryType


def test_unpooled_10x_flex_4plex_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.UNPOOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X Flex 4-plex unpooled libraries")
    samples = ["Unpooled_1", "Unpooled_2", "Unpooled_3", "Unpooled_4", "Unpooled_5"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)
    wf.service(C.ServiceType.TENX_SC_4_PLEX_FLEX, next_step="define-multiplexed-samples")
    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [[s, ""] for s in samples],
    ), next_step="flex-annotation")

    flex_columns = ["Sample Name", "Multiplexing Pool", "Barcode ID"]
    wf.post("flex-annotation", spreadsheet(flex_columns, [
        ["Unpooled_1", "flex_pool_1", "BC001"], ["Unpooled_2", "flex_pool_1", "BC002"],
        ["Unpooled_3", "flex_pool_1", "BC003"], ["Unpooled_4", "flex_pool_1", ""],
        ["Unpooled_5", "flex_pool_2", "BC001"],
    ]), status=202)  # libraries are prepared: every sample needs its probe barcode

    def flex_rows(barcode_4: str) -> list[list[str]]:
        return [
            ["Unpooled_1", "flex_pool_1", "BC001"], ["Unpooled_2", "flex_pool_1", "BC002"],
            ["Unpooled_3", "flex_pool_1", "BC003"], ["Unpooled_4", "flex_pool_1", barcode_4],
            ["Unpooled_5", "flex_pool_2", "BC001"],  # same barcode in another pool is fine
        ]

    wf.post("flex-annotation", spreadsheet(flex_columns, flex_rows("BC005")), status=202)  # 4-plex has BC001-BC004 only
    wf.post("flex-annotation", spreadsheet(flex_columns, flex_rows("Probe-4")), status=202)  # not a probe barcode
    wf.post("flex-annotation", spreadsheet(flex_columns, flex_rows("BC000")), status=202)  # not a probe barcode
    wf.post("flex-annotation", spreadsheet(flex_columns, flex_rows("bc2")), status=202)  # 'bc2' == 'BC002', duplicate in pool
    wf.post("flex-annotation", spreadsheet(flex_columns, flex_rows(" bc4 ")), next_step="complete-s-a-s")  # normalised to 'BC004'

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    gex = L.TENX_SC_GEX_FLEX.identifier
    assert set(libraries) == {f"flex_pool_1_{gex}", f"flex_pool_2_{gex}"}
    for library in libraries.values():
        assert library.pool_id is None
        assert library.indices == []
        assert library.mux_type == C.MUXType.TENX_FLEX_PROBE
    assert linked_samples(libraries[f"flex_pool_1_{gex}"]) == {f"Unpooled_{i}": {"barcode": f"BC00{i}"} for i in range(1, 5)}
    assert linked_samples(libraries[f"flex_pool_2_{gex}"]) == {"Unpooled_5": {"barcode": "BC001"}}
