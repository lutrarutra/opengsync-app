"""LibraryAnnotationWorkflow: raw samples, 10X 3' GEX with on-chip multiplexing (OCM)."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, libraries_by_name, linked_samples, spreadsheet

L = C.LibraryType


def test_raw_10x_3p_ocm_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X 3' OCM raw samples")

    samples = ["OCM_1", "OCM_2", "OCM_3", "OCM_4", "OCM_5"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)

    wf.service(
        C.ServiceType.TENX_SC_GEX_3PRIME,
        next_step="define-multiplexed-samples",
        additional_services__ocm_multiplexing="on",
    )
    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"],
        [["OCM_1", "Chip_1"], ["OCM_2", "Chip_1"], ["OCM_3", "Chip_1"], ["OCM_4", "Chip_1"], ["OCM_5", "Chip_2"]],
    ), next_step="complete-s-a-s")  # raw samples: OCM barcodes are assigned in the lab

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    gex = L.TENX_SC_GEX_3PRIME.identifier
    assert set(libraries) == {f"Chip_1_{gex}", f"Chip_2_{gex}"}
    for library in libraries.values():
        assert library.mux_type == C.MUXType.TENX_ON_CHIP
    assert linked_samples(libraries[f"Chip_1_{gex}"]) == {s: {"barcode": None} for s in samples[:4]}
    assert linked_samples(libraries[f"Chip_2_{gex}"]) == {"OCM_5": {"barcode": None}}
