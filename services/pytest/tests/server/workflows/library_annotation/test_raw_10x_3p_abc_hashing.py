"""LibraryAnnotationWorkflow: raw samples, 10X 3' GEX multiplexed with antibody-based cell hashing (ABC hash)."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, libraries_by_name, linked_samples, spreadsheet,
    assert_features_only_on_abc_libraries,
)

L = C.LibraryType


def test_raw_10x_3p_abc_hashing_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X 3' ABC hashing raw samples")

    samples = ["Hash_1", "Hash_2", "Hash_3"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)

    wf.service(
        C.ServiceType.TENX_SC_GEX_3PRIME,
        status=202,
        optional_assays__antibody_capture="on",
        optional_assays__antibody_capture_kit="TotalSeq-A",
        optional_assays__antibody_multiplexing="on",
        additional_services__ocm_multiplexing="on",
    )  # cannot combine antibody hashing and on-chip multiplexing
    wf.service(
        C.ServiceType.TENX_SC_GEX_3PRIME,
        next_step="define-multiplexed-samples",
        optional_assays__antibody_capture="on",
        optional_assays__antibody_capture_kit="TotalSeq-A",
        optional_assays__antibody_multiplexing="on",
    )

    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"],
        [[s, "Hash_Pool"] for s in samples],
    ), next_step="oligo-mux-annotation")

    hashtags = {"Hash_1": "GTCAACTCTTTAGCG", "Hash_2": "TGATGGCCTATTGGG", "Hash_3": "TTCCGCCTCTCTTTG"}
    wf.post("oligo-mux-annotation", spreadsheet(
        ["Sample Name", "Multiplexing Pool", "Kit", "Feature", "Sequence", "Pattern", "Read"],
        [[s, "Hash_Pool", "", "", hashtags[s], "5PNNNNNNNNNN(BC)", "R2"] for s in samples],
    ), next_step="feature-annotation")

    wf.post("feature-annotation", spreadsheet(
        ["Sample Name", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"],
        [["Hash_Pool", "", "", "CD45", "TCCCTTGCGATTTAC", "5PNNNNNNNNNN(BC)", "R2"]],
    ), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    gex = f"Hash_Pool_{L.TENX_SC_GEX_3PRIME.identifier}"
    abc = f"Hash_Pool_{L.TENX_ANTIBODY_CAPTURE.identifier}"
    # Hashing is read from the antibody-capture library, so there is no separate multiplexing-oligo library.
    assert set(libraries) == {gex, abc}
    for name in [gex, abc]:
        assert libraries[name].mux_type == C.MUXType.TENX_ABC_HASH
        assert linked_samples(libraries[name]) == {
            s: {"barcode": hashtags[s], "pattern": "5PNNNNNNNNNN(BC)", "read": "R2"} for s in samples
        }
    assert [f.name for f in libraries[abc].features] == ["CD45"]
    assert_features_only_on_abc_libraries(libraries)
