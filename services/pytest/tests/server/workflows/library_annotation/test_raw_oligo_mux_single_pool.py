"""LibraryAnnotationWorkflow: raw samples, 10X 3' oligo multiplexing with a single user-named pool."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, libraries_by_name, spreadsheet

L = C.LibraryType


def test_raw_oligo_mux_single_user_pool_keeps_name(
    client, session: SyncSession, user, user_token,
):
    """A single user-typed pool name must be kept verbatim (it used to crash / get its suffix stripped)."""
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X 3' single CMO pool raw")
    wf.samples([["CMO_A", HUMAN], ["CMO_B", HUMAN]])
    wf.attributes(["CMO_A", "CMO_B"])
    wf.service(
        C.ServiceType.TENX_SC_GEX_3PRIME, next_step="define-multiplexed-samples",
        additional_services__oligo_multiplexing="on",
        additional_services__oligo_multiplexing_kit="CellPlex",
    )
    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [["CMO_A", "my_cmo_pool"], ["CMO_B", "my_cmo_pool"]],
    ), next_step="oligo-mux-annotation")
    wf.post("oligo-mux-annotation", spreadsheet(
        ["Sample Name", "Multiplexing Pool", "Kit", "Feature", "Sequence", "Pattern", "Read"],
        [
            ["CMO_A", "my_cmo_pool", "", "", "ATGAGGAATTCCTGC", "5PNNNNNNNNNN(BC)", "R2"],
            ["CMO_B", "my_cmo_pool", "", "", "CATGCCAATAGAGCG", "5PNNNNNNNNNN(BC)", "R2"],
        ],
    ), next_step="complete-s-a-s")
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == {
        f"my_cmo_pool_{L.TENX_SC_GEX_3PRIME.identifier}",
        f"my_cmo_pool_{L.TENX_MUX_OLIGO.identifier}",
    }
