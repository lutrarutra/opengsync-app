"""LibraryAnnotationWorkflow: service types not covered by the dedicated scenario files.

Raw samples go straight from select-service to completion unless the service multiplexes
(Flex 4-/16-plex/Apex → define-multiplexed-samples). Pooled libraries add pool annotation,
pool mapping and index entry; 10X ATAC libraries use the four-sequence ATAC index step
instead of the standard barcode input.
"""

import pytest

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, ATAC_BARCODE_COLUMNS, pool_mapping,
    libraries_by_name, linked_samples, spreadsheet,
)

L = C.LibraryType
S = C.ServiceType

# One library per sample; no service-specific steps.
SINGLE_LIBRARY_SERVICES = [
    S.WGS, S.WES, S.WG_BS_SEQ, S.RR_BS_SEQ, S.WG_EM_SEQ, S.RR_EM_SEQ,
    S.ATAC_SEQ, S.ARTIC_SARS_COV_2, S.IMMUNE_SEQ, S.TENX_SC_SINGLE_PLEX_FLEX,
]
CUSTOM_MATCH = {"i7_kit": "0", "i7_option": "forward", "i7_primer": "AATGATACGGCGACCACCGA"}
ATAC_SEQUENCES = ["AAACGGCG", "CCTACCAT", "GGCGTTTC", "TTGTAAGA"]


def _start(client, session: SyncSession, user, token: str, submission_type: C.SubmissionType, title: str, samples: list[str]):
    seq_request = create_seq_request(session, user, submission_type=submission_type)
    session.commit()
    wf = AnnotationWorkflow(client, token, seq_request.id)
    wf.begin()
    wf.project(title)
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)
    return seq_request, wf


def _assert_libraries(session: SyncSession, seq_request, service: C.ServiceType, expected: dict[str, tuple[C.LibraryType, set[str]]]):
    """``expected`` maps library name → (library type, linked sample names)."""
    libraries = libraries_by_name(session, seq_request.id)
    assert set(libraries) == set(expected)
    for name, (library_type, samples) in expected.items():
        library = libraries[name]
        assert library.type == library_type, name
        assert library.service_type == service, name
        assert set(linked_samples(library)) == samples, name
    return libraries


# ── Raw samples ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("service", SINGLE_LIBRARY_SERVICES + [S.TENX_SC_ATAC], ids=lambda s: s.name)
def test_raw_single_library_service(client, session: SyncSession, user, user_token, service: C.ServiceType):
    samples = ["Raw_S1", "Raw_S2"]
    seq_request, wf = _start(client, session, user, user_token, C.SubmissionType.RAW_SAMPLES, f"Raw {service.abbreviation}", samples)

    wf.service(service, next_step="complete-s-a-s")
    wf.complete()
    wf.assert_cleaned_up()

    (library_type,) = service.library_types
    libraries = _assert_libraries(session, seq_request, service, {
        f"{s}_{library_type.identifier}": (library_type, {s}) for s in samples
    })
    for library in libraries.values():
        assert library.pool_id is None
        assert library.indices == []
        assert library.mux_type is None


def test_raw_10x_multiome(client, session: SyncSession, user, user_token):
    seq_request, wf = _start(client, session, user, user_token, C.SubmissionType.RAW_SAMPLES, "Raw 10X Multiome", ["Nuc_1"])

    wf.service(S.TENX_SC_MULTIOME, next_step="complete-s-a-s")
    wf.complete()

    _assert_libraries(session, seq_request, S.TENX_SC_MULTIOME, {
        f"Nuc_1_{L.TENX_SC_GEX_3PRIME.identifier}": (L.TENX_SC_GEX_3PRIME, {"Nuc_1"}),
        f"Nuc_1_{L.TENX_SC_ATAC.identifier}": (L.TENX_SC_ATAC, {"Nuc_1"}),
    })


def test_raw_10x_flex_apex(client, session: SyncSession, user, user_token):
    """Flex Apex multiplexes with probe barcodes like 4-/16-plex; raw samples get no barcode yet."""
    samples = ["Apex_1", "Apex_2", "Apex_3"]
    seq_request, wf = _start(client, session, user, user_token, C.SubmissionType.RAW_SAMPLES, "Raw 10X Flex Apex", samples)

    wf.service(S.TENX_SC_FLEX_V2, next_step="define-multiplexed-samples")
    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [[s, "Apex_Pool"] for s in samples],
    ), next_step="complete-s-a-s")
    wf.complete()

    gex = f"Apex_Pool_{L.TENX_SC_GEX_FLEX.identifier}"
    libraries = _assert_libraries(session, seq_request, S.TENX_SC_FLEX_V2, {gex: (L.TENX_SC_GEX_FLEX, set(samples))})
    assert libraries[gex].mux_type == C.MUXType.TENX_FLEX_PROBE
    assert linked_samples(libraries[gex]) == {s: {"barcode": None} for s in samples}


# ── Pooled libraries ────────────────────────────────────────────────────────


def _pool_and_index(wf: AnnotationWorkflow, libraries: list[str], pool: str, next_step: str = "complete-s-a-s") -> None:
    """Put every library in ``pool`` and give each a distinct custom i7 index."""
    wf.post("pooled-library-annotation", spreadsheet(
        ["Library Name", "Pool"], [[name, pool] for name in libraries],
    ), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping([pool]), next_step="barcode-input")
    i7 = ["ACGTACGTAC", "TGCATGCATG", "GGGGCCCCAA", "TTTTAAAAGG"]
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [name, "", "", "", i7[i], "", "", ""] for i, name in enumerate(libraries)
    ]), next_step="barcode-match")
    wf.post("barcode-match", CUSTOM_MATCH, next_step=next_step)


@pytest.mark.parametrize("service", SINGLE_LIBRARY_SERVICES, ids=lambda s: s.name)
def test_pooled_single_library_service(client, session: SyncSession, user, user_token, service: C.ServiceType):
    samples = ["Pool_S1", "Pool_S2"]
    seq_request, wf = _start(client, session, user, user_token, C.SubmissionType.POOLED_LIBRARIES, f"Pooled {service.abbreviation}", samples)
    (library_type,) = service.library_types
    names = [f"{s}_{library_type.identifier}" for s in samples]

    wf.service(service, next_step="pooled-library-annotation")
    _pool_and_index(wf, names, "Svc_Pool")
    wf.complete()
    wf.assert_cleaned_up()

    libraries = _assert_libraries(session, seq_request, service, {
        name: (library_type, {s}) for name, s in zip(names, samples)
    })
    for library in libraries.values():
        assert library.pool is not None and library.pool.name == "Svc_Pool"
        assert library.index_type == C.IndexType.SINGLE_INDEX_I7
        assert len(library.indices) == 1


def test_pooled_10x_5prime(client, session: SyncSession, user, user_token):
    seq_request, wf = _start(client, session, user, user_token, C.SubmissionType.POOLED_LIBRARIES, "Pooled 10X 5'", ["Imm_1"])
    gex = f"Imm_1_{L.TENX_SC_GEX_5PRIME.identifier}"
    vdj = f"Imm_1_{L.TENX_VDJ_T.identifier}"

    wf.service(S.TENX_SC_GEX_5PRIME, next_step="pooled-library-annotation", optional_assays__vdj_t="on")
    _pool_and_index(wf, [gex, vdj], "Imm_Pool")
    wf.complete()

    libraries = _assert_libraries(session, seq_request, S.TENX_SC_GEX_5PRIME, {
        gex: (L.TENX_SC_GEX_5PRIME, {"Imm_1"}),
        vdj: (L.TENX_VDJ_T, {"Imm_1"}),
    })
    assert libraries[gex].pool_id == libraries[vdj].pool_id


def test_pooled_10x_atac(client, session: SyncSession, user, user_token):
    """ATAC-only libraries skip standard barcode input and barcode matching."""
    seq_request, wf = _start(client, session, user, user_token, C.SubmissionType.POOLED_LIBRARIES, "Pooled 10X ATAC", ["Atac_1"])
    atac = f"Atac_1_{L.TENX_SC_ATAC.identifier}"

    wf.service(S.TENX_SC_ATAC, next_step="pooled-library-annotation")
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[atac, "Atac_Pool"]]), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["Atac_Pool"]), next_step="t-e-n-x-a-t-a-c-barcode-input")
    wf.post("t-e-n-x-a-t-a-c-barcode-input", spreadsheet(ATAC_BARCODE_COLUMNS, [
        [atac, "", "", "", *ATAC_SEQUENCES],
    ]), next_step="complete-s-a-s")
    wf.complete()

    libraries = _assert_libraries(session, seq_request, S.TENX_SC_ATAC, {atac: (L.TENX_SC_ATAC, {"Atac_1"})})
    assert libraries[atac].index_type == C.IndexType.TENX_ATAC_INDEX
    assert sorted(i.sequence_i7 for i in libraries[atac].indices) == sorted(ATAC_SEQUENCES)


def test_pooled_openst(client, session: SyncSession, user, user_token):
    seq_request, wf = _start(client, session, user, user_token, C.SubmissionType.POOLED_LIBRARIES, "Pooled Open-ST", ["Section_1"])
    openst = f"Section_1_{L.OPENST.identifier}"

    wf.service(S.OPENST, next_step="pooled-library-annotation")
    _pool_and_index(wf, [openst], "OpenST_Pool", next_step="open-s-t-annotation")
    wf.post("open-s-t-annotation", {
        **spreadsheet(["Sample Name", "Image"], [["Section_1", "s1.tif"]]),
        "instructions": "Images on the share",
    }, next_step="complete-s-a-s")
    wf.complete()

    libraries = _assert_libraries(session, seq_request, S.OPENST, {openst: (L.OPENST, {"Section_1"})})
    assert libraries[openst].properties == {"image": "s1.tif"}
    assert libraries[openst].pool is not None


@pytest.mark.parametrize("service, barcodes", [
    (S.TENX_SC_4_PLEX_FLEX, ["BC001", "BC002", "BC004"]),
    (S.TENX_SC_FLEX_V2, ["BC001", "BC017", "BC032"]),  # Apex has no 16/4-plex upper bound
], ids=["4_PLEX", "APEX"])
def test_pooled_10x_flex_multiplexed(client, session: SyncSession, user, user_token, service: C.ServiceType, barcodes: list[str]):
    samples = ["Flex_1", "Flex_2", "Flex_3"]
    seq_request, wf = _start(client, session, user, user_token, C.SubmissionType.POOLED_LIBRARIES, f"Pooled {service.abbreviation}", samples)

    wf.service(service, next_step="define-multiplexed-samples")
    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [[s, "FlexMux"] for s in samples],
    ), next_step="flex-annotation")
    wf.post("flex-annotation", spreadsheet(
        ["Sample Name", "Multiplexing Pool", "Barcode ID"],
        [[s, "FlexMux", bc] for s, bc in zip(samples, barcodes)],
    ), next_step="pooled-library-annotation")
    gex = f"FlexMux_{L.TENX_SC_GEX_FLEX.identifier}"
    _pool_and_index(wf, [gex], "Flex_Seq_Pool")
    wf.complete()

    libraries = _assert_libraries(session, seq_request, service, {gex: (L.TENX_SC_GEX_FLEX, set(samples))})
    assert libraries[gex].mux_type == C.MUXType.TENX_FLEX_PROBE
    assert linked_samples(libraries[gex]) == {s: {"barcode": bc} for s, bc in zip(samples, barcodes)}


def test_pooled_10x_flex_4plex_rejects_barcode_above_4(client, session: SyncSession, user, user_token):
    samples = ["Flex_1", "Flex_2"]
    _, wf = _start(client, session, user, user_token, C.SubmissionType.POOLED_LIBRARIES, "Pooled Flex 4-plex bounds", samples)

    wf.service(S.TENX_SC_4_PLEX_FLEX, next_step="define-multiplexed-samples")
    wf.post("define-multiplexed-samples", spreadsheet(
        ["Sample Name", "Multiplexing Pool"], [[s, "FlexMux"] for s in samples],
    ), next_step="flex-annotation")
    wf.post("flex-annotation", spreadsheet(
        ["Sample Name", "Multiplexing Pool", "Barcode ID"], [["Flex_1", "FlexMux", "BC001"], ["Flex_2", "FlexMux", "BC005"]],
    ), status=202)
