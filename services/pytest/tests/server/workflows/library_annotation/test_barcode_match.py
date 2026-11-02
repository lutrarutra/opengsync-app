"""LibraryAnnotationWorkflow barcode match: kit matching per index (see BarcodeMatchMixin).

A kit is offered for i7 (i5) only if it contains every i7 (i5) sequence entered, in forward or
in reverse complement orientation; otherwise the only option is Custom. i7 and i5 are matched
independently, so they may come from different kits or one may be Custom.
"""

import re
import uuid
from html import unescape

import pytest

from opengsync_db import SyncSession, models, categories as C, queries as Q

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, libraries_by_name, pool_mapping, spreadsheet,
)

L = C.LibraryType
BT = C.BarcodeType
RC = models.Barcode.reverse_complement
PRIMER = "AATGATACGGCGACCACCGA"
I7 = ["ACGTACGTAA", "TTGGCCAATG"]
I5 = ["GGTTCCAACA", "CATCATCAGG"]
OTHER = "GAGAGAGATT"


def _kit(session: SyncSession, adapters: list[list[tuple[C.BarcodeType, str]]], type=C.IndexType.DUAL_INDEX) -> models.IndexKit:
    """One adapter per entry; barcodes are named <type>_<n>."""
    _uuid = str(uuid.uuid4())
    kit = session.save(Q.index_kit.create(name=_uuid, identifier=_uuid[:12], type=type, supported_protocol_ids=[]), flush=True)
    for n, barcodes in enumerate(adapters):
        well = None if type == C.IndexType.COMBINATORIAL_DUAL_INDEX else f"A{n + 1}"
        adapter = session.save(Q.adapter.create(index_kit=kit, well=well), flush=True)
        for barcode_type, sequence in barcodes:
            session.save(Q.barcode.create(
                name=f"{barcode_type.name}_{n}", sequence=sequence, well=well, type=barcode_type, adapter=adapter,
            ), flush=True)
    session.commit()
    return kit


def _dual(*pairs: tuple[str, str]) -> list[list[tuple[C.BarcodeType, str]]]:
    return [[(BT.INDEX_I7, i7), (BT.INDEX_I5, i5)] for i7, i5 in pairs]


def _to_barcode_match(client, session: SyncSession, user, token: str, i7: list[str], i5: list[str] | None = None):
    """Two pooled bulk RNA-seq libraries with the given sequences; returns (wf, libraries, barcode-match response)."""
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()
    wf = AnnotationWorkflow(client, token, seq_request.id)
    wf.begin()
    wf.project("Barcode match")
    samples = [f"BM_{n}" for n in range(len(i7))]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)
    wf.service(C.ServiceType.BULK_RNA_SEQ, next_step="pooled-library-annotation")
    libs = [f"{s}_{L.BULK_RNA_SEQ.identifier}" for s in samples]
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[lib, "BM_Pool"] for lib in libs]), next_step="pool-mapping")
    wf.post("pool-mapping", pool_mapping(["BM_Pool"]), next_step="barcode-input")
    response = wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [lib, "", "", "", i7[n], "", "", i5[n] if i5 else ""] for n, lib in enumerate(libs)
    ]), next_step="barcode-match")
    return wf, seq_request, libs, response


def _options(response, name: str) -> dict[str, str]:
    """value -> label of the <select name=...> options."""
    select = re.search(rf'<select[^>]*name="{name}"[^>]*>(.*?)</select>', response.text, re.S)
    assert select, f"select {name} not rendered"
    return {v: " ".join(unescape(label).split()) for v, label in re.findall(r'<option value="([^"]*)"[^>]*>(.*?)</option>', select.group(1), re.S)}


def _selected(response, name: str) -> str | None:
    select = re.search(rf'<select[^>]*name="{name}"[^>]*>(.*?)</select>', response.text, re.S)
    assert select
    selected = re.findall(r'<option value="([^"]*)"\s*selected', select.group(1))
    return selected[0] if selected else None


def _indices(session: SyncSession, seq_request, libs: list[str]) -> list[tuple]:
    libraries = libraries_by_name(session, seq_request.id)
    return [
        (i.name_i7, i.sequence_i7, i.index_kit_i7_id, i.name_i5, i.sequence_i5, i.index_kit_i5_id, i.orientation)
        for lib in libs for i in libraries[lib].indices
    ]


# ── Offered options ─────────────────────────────────────────────────────────


def test_only_kits_containing_all_sequences_are_offered(client, session: SyncSession, user, user_token):
    full = _kit(session, _dual((I7[0], I5[0]), (I7[1], I5[1])))
    partial = _kit(session, _dual((I7[0], I5[0]), (OTHER, OTHER)))
    i5_only = _kit(session, _dual((OTHER, I5[0]), (RC(OTHER), I5[1])))

    _, _, _, response = _to_barcode_match(client, session, user, user_token, I7, I5)

    assert set(_options(response, "i7_kit")) == {"0", str(full.id)}
    assert set(_options(response, "i5_kit")) == {"0", str(full.id), str(i5_only.id)}
    assert str(partial.id) not in _options(response, "i7_kit")


def test_sequences_from_two_kits_offer_only_custom(client, session: SyncSession, user, user_token):
    _kit(session, _dual((I7[0], I5[0])))
    _kit(session, _dual((I7[1], I5[1])))

    _, _, _, response = _to_barcode_match(client, session, user, user_token, I7, I5)

    assert set(_options(response, "i7_kit")) == {"0"}
    assert set(_options(response, "i5_kit")) == {"0"}


def test_kit_matching_both_orientations_is_offered_twice_with_distinct_values(client, session: SyncSession, user, user_token):
    kit = _kit(session, _dual((I7[0], I5[0]), (I7[1], I5[1]), (RC(I7[0]), OTHER), (RC(I7[1]), RC(OTHER))))

    _, _, _, response = _to_barcode_match(client, session, user, user_token, I7, I5)

    options = _options(response, "i7_kit")
    assert set(options) == {"0", str(kit.id), f"{kit.id}:rc"}
    assert options[f"{kit.id}:rc"] == options[str(kit.id)] + " (Reverse Complement)"
    # The kit tab is listed once
    assert response.text.count(f'id="index_kit-{kit.id}-tab"') == 1


# ── Submit ──────────────────────────────────────────────────────────────────


def test_forward_kit_sets_names_kit_and_validated_orientation(client, session: SyncSession, user, user_token):
    kit = _kit(session, _dual((I7[0], I5[0]), (I7[1], I5[1])))
    wf, seq_request, libs, _ = _to_barcode_match(client, session, user, user_token, I7, I5)

    wf.post("barcode-match", {"i7_kit": str(kit.id), "i5_kit": str(kit.id)}, next_step="library-protocol-annotation")
    wf.protocols()
    wf.complete()

    F = C.BarcodeOrientation.FORWARD
    assert _indices(session, seq_request, libs) == [
        ("INDEX_I7_0", I7[0], kit.id, "INDEX_I5_0", I5[0], kit.id, F),
        ("INDEX_I7_1", I7[1], kit.id, "INDEX_I5_1", I5[1], kit.id, F),
    ]


def test_reverse_complement_kit_stores_kit_orientation(client, session: SyncSession, user, user_token):
    kit = _kit(session, _dual((RC(I7[0]), RC(I5[0])), (RC(I7[1]), RC(I5[1]))))
    wf, seq_request, libs, response = _to_barcode_match(client, session, user, user_token, I7, I5)
    assert set(_options(response, "i7_kit")) == {"0", f"{kit.id}:rc"}

    wf.post("barcode-match", {"i7_kit": f"{kit.id}:rc", "i5_kit": f"{kit.id}:rc"}, next_step="library-protocol-annotation")
    wf.protocols()
    wf.complete()

    F = C.BarcodeOrientation.FORWARD
    assert _indices(session, seq_request, libs) == [
        ("INDEX_I7_0", RC(I7[0]), kit.id, "INDEX_I5_0", RC(I5[0]), kit.id, F),
        ("INDEX_I7_1", RC(I7[1]), kit.id, "INDEX_I5_1", RC(I5[1]), kit.id, F),
    ]


def test_forward_selection_of_kit_matching_both_orientations_keeps_sequences(client, session: SyncSession, user, user_token):
    """Regression: forward and RC options shared the kit id, so the forward choice was treated as RC."""
    kit = _kit(session, _dual((I7[0], I5[0]), (I7[1], I5[1]), (RC(I7[0]), OTHER), (RC(I7[1]), RC(OTHER))))
    wf, seq_request, libs, _ = _to_barcode_match(client, session, user, user_token, I7, I5)

    wf.post("barcode-match", {"i7_kit": str(kit.id), "i5_kit": str(kit.id)}, next_step="library-protocol-annotation")
    wf.protocols()
    wf.complete()

    assert [(i[0], i[1]) for i in _indices(session, seq_request, libs)] == [("INDEX_I7_0", I7[0]), ("INDEX_I7_1", I7[1])]


def test_i7_and_i5_from_different_kits(client, session: SyncSession, user, user_token):
    kit_i7 = _kit(session, _dual((I7[0], OTHER), (I7[1], RC(OTHER))))
    kit_i5 = _kit(session, _dual((OTHER, I5[0]), (RC(OTHER), I5[1])))
    wf, seq_request, libs, _ = _to_barcode_match(client, session, user, user_token, I7, I5)

    wf.post("barcode-match", {"i7_kit": str(kit_i7.id), "i5_kit": str(kit_i5.id)}, next_step="library-protocol-annotation")
    wf.protocols()
    wf.complete()

    F = C.BarcodeOrientation.FORWARD
    assert _indices(session, seq_request, libs) == [
        ("INDEX_I7_0", I7[0], kit_i7.id, "INDEX_I5_0", I5[0], kit_i5.id, F),
        ("INDEX_I7_1", I7[1], kit_i7.id, "INDEX_I5_1", I5[1], kit_i5.id, F),
    ]


def test_i7_kit_with_custom_i5(client, session: SyncSession, user, user_token):
    kit = _kit(session, _dual((I7[0], OTHER), (I7[1], RC(OTHER))))
    wf, seq_request, libs, _ = _to_barcode_match(client, session, user, user_token, I7, I5)

    wf.post("barcode-match", {
        "i7_kit": str(kit.id), "i5_kit": "0", "i5_option": "rc", "i5_primer": PRIMER,
    }, next_step="library-protocol-annotation")
    wf.protocols()
    wf.complete()

    indices = _indices(session, seq_request, libs)
    assert [(i[0], i[1], i[2], i[4], i[5]) for i in indices] == [
        ("INDEX_I7_0", I7[0], kit.id, RC(I5[0]), None),
        ("INDEX_I7_1", I7[1], kit.id, RC(I5[1]), None),
    ]
    # The orientation is only validated if both indices come from a kit
    assert all(i[6] == C.BarcodeOrientation.FORWARD_NOT_VALIDATED for i in indices)


@pytest.mark.parametrize("match", [
    {"i7_kit": "{kit}", "i5_kit": "0", "i5_option": "idk", "i5_primer": PRIMER},
    {"i5_kit": "{kit}", "i7_kit": "0", "i7_option": "idk", "i7_primer": PRIMER},
], ids=["kit-i7", "kit-i5"])
def test_kit_with_unknown_orientation_of_other_index_is_not_validated(client, session: SyncSession, user, user_token, match):
    """The index is validated only if both i7 and i5 are; an unknown one needs a manual check."""
    kit = _kit(session, _dual((I7[0], I5[0]), (I7[1], I5[1])))
    wf, seq_request, libs, _ = _to_barcode_match(client, session, user, user_token, I7, I5)

    wf.post("barcode-match", {k: v.format(kit=kit.id) for k, v in match.items()}, next_step="library-protocol-annotation")
    wf.protocols()
    wf.complete()

    assert [i[6] for i in _indices(session, seq_request, libs)] == [C.BarcodeOrientation.FORWARD_NOT_VALIDATED] * 2


@pytest.mark.parametrize("kit_type, adapters", [
    # i5 shared between adapters
    (C.IndexType.DUAL_INDEX, _dual((I7[0], I5[0]), (I7[1], I5[0]))),
    (C.IndexType.COMBINATORIAL_DUAL_INDEX, [[(BT.INDEX_I7, I7[0])], [(BT.INDEX_I7, I7[1])], [(BT.INDEX_I5, I5[0])]]),
], ids=["shared-i5", "combinatorial"])
def test_kit_with_repeated_or_missing_sequences(client, session: SyncSession, user, user_token, kit_type, adapters):
    """Regression: name lookup crashed on kits where a sequence occurs in several adapters."""
    kit = _kit(session, adapters, type=kit_type)
    wf, seq_request, libs, _ = _to_barcode_match(client, session, user, user_token, I7, [I5[0], I5[0]])

    wf.post("barcode-match", {"i7_kit": str(kit.id), "i5_kit": str(kit.id)}, next_step="library-protocol-annotation")
    wf.protocols()
    wf.complete()

    assert [(i[1], i[2], i[4], i[5]) for i in _indices(session, seq_request, libs)] == [
        (I7[0], kit.id, I5[0], kit.id), (I7[1], kit.id, I5[0], kit.id),
    ]


# ── Validation ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("field", ["i7_kit", "i5_kit"])
def test_kit_not_offered_is_rejected(client, session: SyncSession, user, user_token, field):
    """Regression: a kit id that was not offered crashed the submit (KeyError) instead of a form error."""
    full = _kit(session, _dual((I7[0], I5[0]), (I7[1], I5[1])))
    partial = _kit(session, _dual((I7[0], I5[0])))
    wf, _, _, _ = _to_barcode_match(client, session, user, user_token, I7, I5)

    data = {"i7_kit": str(full.id), "i5_kit": str(full.id), field: str(partial.id)}
    response = wf.post("barcode-match", data, status=None)

    assert response.status_code != 200 or wf.rendered_step(response) == "barcode-match"
    index = field.split("_")[0]
    assert f"The selected kit does not contain all {index} sequences." in response.text


def test_orientation_not_offered_is_rejected(client, session: SyncSession, user, user_token):
    kit = _kit(session, _dual((I7[0], I5[0]), (I7[1], I5[1])))
    wf, _, _, _ = _to_barcode_match(client, session, user, user_token, I7, I5)

    response = wf.post("barcode-match", {"i7_kit": f"{kit.id}:rc", "i5_kit": str(kit.id)}, status=None)

    assert "The selected kit does not contain all i7 sequences." in response.text


def test_kit_must_be_selected(client, session: SyncSession, user, user_token):
    wf, _, _, _ = _to_barcode_match(client, session, user, user_token, I7, I5)

    response = wf.post("barcode-match", {}, status=None)

    assert "Please select an i7 kit or choose Custom." in response.text
    assert "Please select an i5 kit or choose Custom." in response.text


def test_single_index_does_not_require_i5(client, session: SyncSession, user, user_token):
    kit = _kit(session, [[(BT.INDEX_I7, I7[0])], [(BT.INDEX_I7, I7[1])]], type=C.IndexType.SINGLE_INDEX_I7)
    wf, seq_request, libs, response = _to_barcode_match(client, session, user, user_token, I7)
    assert set(_options(response, "i7_kit")) == {"0", str(kit.id)}

    wf.post("barcode-match", {"i7_kit": str(kit.id)}, next_step="library-protocol-annotation")
    wf.protocols()
    wf.complete()

    assert [(i[0], i[1], i[2], i[4]) for i in _indices(session, seq_request, libs)] == [
        ("INDEX_I7_0", I7[0], kit.id, None), ("INDEX_I7_1", I7[1], kit.id, None),
    ]


# ── Back navigation ─────────────────────────────────────────────────────────


def test_back_restores_kit_selection_and_resubmit_does_not_reapply(client, session: SyncSession, user, user_token):
    kit = _kit(session, _dual((RC(I7[0]), I5[0]), (RC(I7[1]), I5[1])))
    wf, seq_request, libs, _ = _to_barcode_match(client, session, user, user_token, I7, I5)
    data = {"i7_kit": f"{kit.id}:rc", "i5_kit": str(kit.id)}
    wf.post("barcode-match", data, next_step="library-protocol-annotation")
    wf.protocols()

    response = wf.back("barcode-match")
    assert _selected(response, "i7_kit") == f"{kit.id}:rc"
    assert _selected(response, "i5_kit") == str(kit.id)

    wf.post("barcode-match", data, next_step="library-protocol-annotation")
    wf.protocols()
    wf.complete()

    # Reverse-complemented once, not twice
    assert [(i[1], i[4]) for i in _indices(session, seq_request, libs)] == [(RC(I7[0]), I5[0]), (RC(I7[1]), I5[1])]
