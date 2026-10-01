"""LibraryAnnotationWorkflow: raw samples, 10X Flex 4-plex with Flex antibody capture and auto-generated pools."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, libraries_by_name, linked_samples, spreadsheet,
    assert_features_only_on_abc_libraries,
)

L = C.LibraryType


def test_raw_10x_flex_4plex_abc_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X Flex 4-plex + ABC raw samples")

    samples = [f"Flex_Sample_{i}" for i in range(1, 7)]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)

    wf.service(
        C.ServiceType.TENX_SC_4_PLEX_FLEX,
        status=202,
        optional_assays__antibody_capture="on",
        optional_assays__antibody_capture_kit="TotalSeq-B",
        optional_assays__antibody_multiplexing="on",
    )  # antibody hashing is not available with Flex
    wf.service(
        C.ServiceType.TENX_SC_4_PLEX_FLEX,
        next_step="define-multiplexed-samples",
        optional_assays__antibody_capture="on",
        optional_assays__antibody_capture_kit="TotalSeq-B",
    )

    # Leaving all pools empty auto-assigns 4 samples per Flex 4-plex pool.
    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"],
        [[s, ""] for s in samples],
    ), next_step="feature-annotation")

    wf.post("feature-annotation", spreadsheet(
        ["Sample Name", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"],
        [
            ["flex_pool_1", "", "", "CD3", "CTCATTGTAACTCCT", "5PNNNNNNNNNN(BC)", "R2"],
            ["flex_pool_2", "", "", "CD3", "CTCATTGTAACTCCT", "5PNNNNNNNNNN(BC)", "R2"],
            ["flex_pool_2", "", "", "CD8", "GCTGCGCTTTCCATT", "5PNNNNNNNNNN(BC)", "R2"],
        ],
    ), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == {
        f"{pool}_{t.identifier}"
        for pool in ["flex_pool_1", "flex_pool_2"]
        for t in [L.TENX_SC_GEX_FLEX, L.TENX_SC_ABC_FLEX]
    }
    for library in libraries.values():
        assert library.mux_type == C.MUXType.TENX_FLEX_PROBE
        assert library.service_type == C.ServiceType.TENX_SC_4_PLEX_FLEX

    for pool, pool_samples in [("flex_pool_1", samples[:4]), ("flex_pool_2", samples[4:])]:
        for t in [L.TENX_SC_GEX_FLEX, L.TENX_SC_ABC_FLEX]:
            # Raw samples: probe barcodes are assigned by the facility, so none yet.
            assert linked_samples(libraries[f"{pool}_{t.identifier}"]) == {s: {"barcode": None} for s in pool_samples}

    assert sorted(f.name for f in libraries[f"flex_pool_1_{L.TENX_SC_ABC_FLEX.identifier}"].features) == ["CD3"]
    assert sorted(f.name for f in libraries[f"flex_pool_2_{L.TENX_SC_ABC_FLEX.identifier}"].features) == ["CD3", "CD8"]
    assert_features_only_on_abc_libraries(libraries)
