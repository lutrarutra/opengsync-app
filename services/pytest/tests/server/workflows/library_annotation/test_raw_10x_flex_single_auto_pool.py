"""LibraryAnnotationWorkflow: raw samples, 10X Flex 16-plex where all samples fit one auto-generated pool."""

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, libraries_by_name, linked_samples, spreadsheet

L = C.LibraryType


def test_raw_10x_flex_single_auto_pool(
    client, session: SyncSession, user, user_token,
):
    """All samples fit one auto-generated pool: the pool is named without a numeric suffix."""
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("10X Flex 16-plex single pool raw")
    samples = ["Flex_A", "Flex_B", "Flex_C"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)
    wf.service(C.ServiceType.TENX_SC_16_PLEX_FLEX, next_step="define-multiplexed-samples")
    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [[s, ""] for s in samples],
    ), next_step="complete-s-a-s")
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == {f"flex_pool_{L.TENX_SC_GEX_FLEX.identifier}"}
    assert set(linked_samples(libraries[f"flex_pool_{L.TENX_SC_GEX_FLEX.identifier}"])) == set(samples)
