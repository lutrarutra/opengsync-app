"""EditKitBarcodesForm and its per-kit-type variants: edit an index kit's barcodes.

As legacy ``index_kits_htmx.edit_barcodes``: admin-only; the form is chosen by kit type
(single index, dual index, combinatorial dual index, 10x ATAC), prefilled with the kit's
barcodes, and submitting replaces all adapters/barcodes. Wells are normalized (``A01`` →
``A1``), whitespace is removed, and optional switches reverse-complement the sequences.

- Single index: well, name and sequence required and unique.
- Dual index: well, i7 and i5 required; a missing i5 name takes the i7 name; well and
  the i7 + i5 pair unique; a name maps to one sequence and vice versa.
- Combinatorial: no wells; name and sequence given together; each i7/i5 is its own adapter.
- 10x ATAC: well, name and four sequences required; well unique.

Legacy's dual-index save raised ``KeyError`` (``row["name"]``); the dual tests assert the
evident intent.
"""

from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
    spreadsheet_payload,
)

PREFIX = "/htmx/index_kits"

SINGLE_COLUMNS = ["Well", "Name", "Sequence"]
DUAL_COLUMNS = ["Well", "Name i7", "Sequence i7", "Name i5", "Sequence i5"]
COMBINATORIAL_COLUMNS = ["Name i7", "Sequence i7", "Name i5", "Sequence i5"]
ATAC_COLUMNS = ["Well", "Name", "Sequence 1", "Sequence 2", "Sequence 3", "Sequence 4"]

I7, I5 = C.BarcodeType.INDEX_I7, C.BarcodeType.INDEX_I5


def _path(index_kit_id: int) -> str:
    return f"{PREFIX}/{index_kit_id}/edit-barcodes"


def _payload(columns: list[str], rows: list[list[Any]], **switches: bool) -> dict[str, str]:
    """Switches are submitted as 'on' when checked, omitted otherwise."""
    return {**spreadsheet_payload(columns, rows), **{name: "on" for name, checked in switches.items() if checked}}


def _kit(session: SyncSession, type: C.IndexTypeEnum, adapters: list[tuple[str | None, list[tuple[Any, str, str]]]]) -> models.IndexKit:
    """``adapters``: (well, [(barcode type, name, sequence), ...]) per adapter."""
    count = session.execute(sa.select(sa.func.count()).select_from(models.IndexKit)).scalar_one()
    kit = session.save(Q.index_kit.create(
        name=f"Kit {type.name} {count}", identifier=f"K{type.id}_{count}", type=type, supported_protocol_ids=[],
    ), flush=True)
    for well, barcodes in adapters:
        adapter = session.save(Q.adapter.create(index_kit=kit, well=well), flush=True)
        for barcode_type, name, sequence in barcodes:
            session.save(Q.barcode.create(name=name, sequence=sequence, well=well, type=barcode_type, adapter=adapter), flush=True)
    session.commit()
    return kit


def _barcodes(session: SyncSession, kit: models.IndexKit) -> list[tuple[str | None, str, str, str]]:
    """Stored barcodes as sorted (well, type name, name, sequence)."""
    session.expire_all()
    rows = session.execute(
        sa.select(models.Barcode).where(models.Barcode.index_kit_id == kit.id)
    ).scalars().all()
    return sorted(((b.well, b.type.name, b.name, b.sequence) for b in rows), key=lambda t: tuple(str(x) for x in t))


def _num_adapters(session: SyncSession, kit: models.IndexKit) -> int:
    session.expire_all()
    return len(session.get_one(Q.index_kit.select(id=kit.id)).adapters)


@pytest.fixture
def single_kit(session: SyncSession) -> models.IndexKit:
    return _kit(session, C.IndexType.SINGLE_INDEX_I7, [("A1", [(I7, "OLD_A1", "AAAACCCC")])])


@pytest.fixture
def dual_kit(session: SyncSession) -> models.IndexKit:
    return _kit(session, C.IndexType.DUAL_INDEX, [("A1", [(I7, "OLD_I7", "AAAACCCC"), (I5, "OLD_I5", "GGGGTTTT")])])


@pytest.fixture
def combinatorial_kit(session: SyncSession) -> models.IndexKit:
    return _kit(session, C.IndexType.COMBINATORIAL_DUAL_INDEX, [
        (None, [(I7, "OLD_I7", "AAAACCCC")]),
        (None, [(I5, "OLD_I5", "GGGGTTTT")]),
    ])


@pytest.fixture
def atac_kit(session: SyncSession) -> models.IndexKit:
    return _kit(session, C.IndexType.TENX_ATAC_INDEX, [
        ("A1", [(I7, "OLD_ATAC", s) for s in ("AAAAAAAA", "CCCCCCCC", "GGGGGGGG", "TTTTTTTT")]),
    ])


# ── Render and dispatch (GET) ───────────────────────────────────────────────


@pytest.mark.parametrize("fixture, columns, texts", [
    ("single_kit", SINGLE_COLUMNS, ["OLD_A1", "AAAACCCC"]),
    ("dual_kit", DUAL_COLUMNS, ["OLD_I7", "OLD_I5", "GGGGTTTT"]),
    ("combinatorial_kit", COMBINATORIAL_COLUMNS, ["OLD_I7", "OLD_I5", "GGGGTTTT"]),
    ("atac_kit", ATAC_COLUMNS, ["OLD_ATAC", "TTTTTTTT"]),
])
def test_render_prefills_barcodes_with_type_columns(
    client: TestClient, request: pytest.FixtureRequest, admin_token: str, fixture: str, columns: list[str], texts: list[str],
):
    kit = request.getfixturevalue(fixture)

    response = get(client, _path(kit.id), admin_token)

    assert response.status_code == 200, response.text
    for text in texts + columns:
        assert text in response.text


def test_columns_do_not_leak_between_kit_types(
    client: TestClient, single_kit: models.IndexKit, dual_kit: models.IndexKit, admin_token: str,
):
    """Each request must get only its kit type's columns, whatever was rendered before."""
    assert get(client, _path(dual_kit.id), admin_token).status_code == 200
    response = get(client, _path(single_kit.id), admin_token)

    assert response.status_code == 200, response.text
    assert "Sequence i7" not in response.text
    assert "Name i5" not in response.text


def test_render_does_not_change_barcodes(client: TestClient, session: SyncSession, dual_kit: models.IndexKit, admin_token: str):
    before = _barcodes(session, dual_kit)
    get(client, _path(dual_kit.id), admin_token)
    assert _barcodes(session, dual_kit) == before


# ── Access ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("token_fixture", ["user_token", "insider_token"])
def test_non_admin_is_denied(
    client: TestClient, session: SyncSession, request: pytest.FixtureRequest, single_kit: models.IndexKit, token_fixture: str,
):
    token = request.getfixturevalue(token_fixture)
    before = _barcodes(session, single_kit)

    assert get(client, _path(single_kit.id), token).status_code == 403
    response = post_form(client, _path(single_kit.id), _payload(SINGLE_COLUMNS, [["B1", "NEW", "ACGTACGT"]]), token=token)
    assert response.status_code == 403
    assert _barcodes(session, single_kit) == before


@pytest.mark.parametrize("token_fixture", ["user_token", "insider_token"])
def test_non_admin_with_invalid_submission_is_still_denied(
    client: TestClient, request: pytest.FixtureRequest, single_kit: models.IndexKit, token_fixture: str,
):
    """The role check must not come after validation (which would render the form back)."""
    token = request.getfixturevalue(token_fixture)
    assert post_form(client, _path(single_kit.id), {}, token=token).status_code == 403


def test_anonymous_is_redirected_to_login(client: TestClient, single_kit: models.IndexKit):
    for response in (get(client, _path(single_kit.id)), post_form(client, _path(single_kit.id), {})):
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")


def test_unknown_kit_is_404(client: TestClient, admin_token: str):
    assert get(client, _path(999999), admin_token).status_code == 404


def test_csrf_mismatch_changes_nothing(client: TestClient, session: SyncSession, single_kit: models.IndexKit, admin_token: str):
    before = _barcodes(session, single_kit)
    response = post_form_csrf_mismatch(client, _path(single_kit.id), _payload(SINGLE_COLUMNS, [["B1", "NEW", "ACGTACGT"]]), token=admin_token)

    assert response.status_code != 204
    assert _barcodes(session, single_kit) == before


# ── Single index ────────────────────────────────────────────────────────────


def test_single_index_replaces_barcodes(client: TestClient, session: SyncSession, single_kit: models.IndexKit, admin_token: str):
    response = post_form(client, _path(single_kit.id), _payload(SINGLE_COLUMNS, [
        ["A01", " NEW 1 ", "ACGT ACGT"], ["B1", "NEW_2", "TTTTGGGG"],
    ]), token=admin_token)

    assert_htmx_redirect(response, f"/index-kits/{single_kit.id}")
    assert_flash(response, "Changes saved!", category="success")
    assert _barcodes(session, single_kit) == [("A1", "INDEX_I7", "NEW1", "ACGTACGT"), ("B1", "INDEX_I7", "NEW_2", "TTTTGGGG")]
    assert _num_adapters(session, single_kit) == 2


def test_single_index_reverse_complement(client: TestClient, session: SyncSession, single_kit: models.IndexKit, admin_token: str):
    response = post_form(client, _path(single_kit.id), _payload(SINGLE_COLUMNS, [["A1", "NEW", "AACCGGTA"]], rc_sequence=True), token=admin_token)

    assert_htmx_redirect(response, f"/index-kits/{single_kit.id}")
    assert _barcodes(session, single_kit) == [("A1", "INDEX_I7", "NEW", "TACCGGTT")]


@pytest.mark.parametrize("rows, message", [
    ([["A1", "N1", "AAAACCCC"], ["A01", "N2", "GGGGTTTT"]], "Duplicate well."),
    ([["A1", "SAME", "AAAACCCC"], ["B1", "SAME", "GGGGTTTT"]], "Duplicate name."),
    ([["A1", "N1", "AAAACCCC"], ["B1", "N2", "AAAACCCC"]], "Duplicate sequence."),
    ([["", "N1", "AAAACCCC"]], "Well is missing."),
    ([["A1", "", "AAAACCCC"]], "Name is missing."),
    ([["A1", "N1", ""]], "Sequence is missing."),
])
def test_single_index_validation(
    client: TestClient, session: SyncSession, single_kit: models.IndexKit, admin_token: str, rows: list, message: str,
):
    before = _barcodes(session, single_kit)
    response = post_form(client, _path(single_kit.id), _payload(SINGLE_COLUMNS, rows), token=admin_token)

    assert_form_invalid(response, message)
    assert _barcodes(session, single_kit) == before


# ── Dual index ──────────────────────────────────────────────────────────────


def test_dual_index_replaces_barcodes(client: TestClient, session: SyncSession, dual_kit: models.IndexKit, admin_token: str):
    response = post_form(client, _path(dual_kit.id), _payload(DUAL_COLUMNS, [
        ["A1", "D701", "ATTACTCG", "D501", "TATAGCCT"],
        ["B01", "D702", "TCCGGAGA", "D502", "ATAGAGGC"],
    ]), token=admin_token)

    assert_htmx_redirect(response, f"/index-kits/{dual_kit.id}")
    assert _barcodes(session, dual_kit) == [
        ("A1", "INDEX_I5", "D501", "TATAGCCT"), ("A1", "INDEX_I7", "D701", "ATTACTCG"),
        ("B1", "INDEX_I5", "D502", "ATAGAGGC"), ("B1", "INDEX_I7", "D702", "TCCGGAGA"),
    ]
    assert _num_adapters(session, dual_kit) == 2


def test_dual_index_missing_i5_name_takes_i7_name(client: TestClient, session: SyncSession, dual_kit: models.IndexKit, admin_token: str):
    response = post_form(client, _path(dual_kit.id), _payload(DUAL_COLUMNS, [["A1", "SI-TT-A1", "ATTACTCG", "", "TATAGCCT"]]), token=admin_token)

    assert_htmx_redirect(response, f"/index-kits/{dual_kit.id}")
    assert _barcodes(session, dual_kit) == [("A1", "INDEX_I5", "SI-TT-A1", "TATAGCCT"), ("A1", "INDEX_I7", "SI-TT-A1", "ATTACTCG")]


@pytest.mark.parametrize("rc_i7, rc_i5, expected_i7, expected_i5", [
    (True, False, "CGAGTAAT", "TATAGCCT"),
    (False, True, "ATTACTCG", "AGGCTATA"),
])
def test_dual_index_reverse_complement_per_index(
    client: TestClient, session: SyncSession, dual_kit: models.IndexKit, admin_token: str,
    rc_i7: bool, rc_i5: bool, expected_i7: str, expected_i5: str,
):
    response = post_form(client, _path(dual_kit.id), _payload(
        DUAL_COLUMNS, [["A1", "N7", "ATTACTCG", "N5", "TATAGCCT"]], rc_sequence_i7=rc_i7, rc_sequence_i5=rc_i5,
    ), token=admin_token)

    assert_htmx_redirect(response, f"/index-kits/{dual_kit.id}")
    assert _barcodes(session, dual_kit) == [("A1", "INDEX_I5", "N5", expected_i5), ("A1", "INDEX_I7", "N7", expected_i7)]


@pytest.mark.parametrize("rows, message", [
    ([["A1", "N1", "AAAACCCC", "M1", "GGGGTTTT"], ["A1", "N2", "CCCCAAAA", "M2", "TTTTGGGG"]], "Duplicate well."),
    ([["A1", "N1", "AAAACCCC", "M1", "GGGGTTTT"], ["B1", "N1", "AAAACCCC", "M1", "GGGGTTTT"]], "Duplicate sequence combination i7 & i5."),
    ([["A1", "N1", "AAAACCCC", "M1", "GGGGTTTT"], ["B1", "N1", "CCCCAAAA", "M2", "TTTTGGGG"]], "Duplicate name i7 with different sequence."),
    ([["A1", "N1", "AAAACCCC", "M1", "GGGGTTTT"], ["B1", "N2", "AAAACCCC", "M2", "TTTTGGGG"]], "Duplicate sequence i7 with different name."),
    ([["", "N1", "AAAACCCC", "M1", "GGGGTTTT"]], "Well is missing."),
    ([["A1", "N1", "", "M1", "GGGGTTTT"]], "Sequence i7 is missing."),
    ([["A1", "N1", "AAAACCCC", "M1", ""]], "Sequence i5 is missing."),
])
def test_dual_index_validation(
    client: TestClient, session: SyncSession, dual_kit: models.IndexKit, admin_token: str, rows: list, message: str,
):
    before = _barcodes(session, dual_kit)
    response = post_form(client, _path(dual_kit.id), _payload(DUAL_COLUMNS, rows), token=admin_token)

    assert_form_invalid(response, message)
    assert _barcodes(session, dual_kit) == before


# ── Combinatorial dual index ────────────────────────────────────────────────


def test_combinatorial_replaces_barcodes(
    client: TestClient, session: SyncSession, combinatorial_kit: models.IndexKit, admin_token: str,
):
    response = post_form(client, _path(combinatorial_kit.id), _payload(COMBINATORIAL_COLUMNS, [
        ["N701", "ATTACTCG", "S502", "CTCTCTAT"],
        ["N702", "TCCGGAGA", "", ""],
    ]), token=admin_token)

    assert_htmx_redirect(response, f"/index-kits/{combinatorial_kit.id}")
    assert _barcodes(session, combinatorial_kit) == [
        (None, "INDEX_I5", "S502", "CTCTCTAT"),
        (None, "INDEX_I7", "N701", "ATTACTCG"),
        (None, "INDEX_I7", "N702", "TCCGGAGA"),
    ]
    # One adapter per barcode
    assert _num_adapters(session, combinatorial_kit) == 3


def test_combinatorial_reverse_complement(
    client: TestClient, session: SyncSession, combinatorial_kit: models.IndexKit, admin_token: str,
):
    response = post_form(client, _path(combinatorial_kit.id), _payload(
        COMBINATORIAL_COLUMNS, [["N701", "ATTACTCG", "S502", "CTCTCTAT"]], rc_sequence_i5=True,
    ), token=admin_token)

    assert_htmx_redirect(response, f"/index-kits/{combinatorial_kit.id}")
    assert _barcodes(session, combinatorial_kit) == [(None, "INDEX_I5", "S502", "ATAGAGAG"), (None, "INDEX_I7", "N701", "ATTACTCG")]


@pytest.mark.parametrize("rows", [
    [["N701", "", "", ""]],
    [["", "ATTACTCG", "", ""]],
    [["", "", "S502", ""]],
    [["N701", "ATTACTCG", "S502", "CTCTCTAT"], ["N701", "ATTACTCG", "S502", "CTCTCTAT"]],
    [["N701", "ATTACTCG", "", ""], ["N701", "TCCGGAGA", "", ""]],
])
def test_combinatorial_validation(
    client: TestClient, session: SyncSession, combinatorial_kit: models.IndexKit, admin_token: str, rows: list,
):
    before = _barcodes(session, combinatorial_kit)
    response = post_form(client, _path(combinatorial_kit.id), _payload(COMBINATORIAL_COLUMNS, rows), token=admin_token)

    assert_form_invalid(response)
    assert _barcodes(session, combinatorial_kit) == before


# ── 10x ATAC ────────────────────────────────────────────────────────────────


def test_atac_replaces_barcodes(client: TestClient, session: SyncSession, atac_kit: models.IndexKit, admin_token: str):
    response = post_form(client, _path(atac_kit.id), _payload(ATAC_COLUMNS, [
        ["A01", "SI-NA-A1", "AAACGGCG", "CCTACCAT", "GGCGTTTC", "TTGTAAGA"],
    ]), token=admin_token)

    assert_htmx_redirect(response, f"/index-kits/{atac_kit.id}")
    assert _barcodes(session, atac_kit) == [
        ("A1", "INDEX_I7", "SI-NA-A1", s) for s in ("AAACGGCG", "CCTACCAT", "GGCGTTTC", "TTGTAAGA")
    ]
    assert _num_adapters(session, atac_kit) == 1


def test_atac_reverse_complement(client: TestClient, session: SyncSession, atac_kit: models.IndexKit, admin_token: str):
    response = post_form(client, _path(atac_kit.id), _payload(
        ATAC_COLUMNS, [["A1", "N", "AAAAAAAC", "CCCCCCCA", "GGGGGGGA", "TTTTTTTA"]], rc_sequence=True,
    ), token=admin_token)

    assert_htmx_redirect(response, f"/index-kits/{atac_kit.id}")
    assert sorted(seq for *_, seq in _barcodes(session, atac_kit)) == ["GTTTTTTT", "TAAAAAAA", "TCCCCCCC", "TGGGGGGG"]


@pytest.mark.parametrize("rows, message", [
    ([["A1", "N1", "AAAAAAAA", "CCCCCCCC", "GGGGGGGG", "TTTTTTTT"], ["A1", "N2", "AAAAAAAC", "CCCCCCCA", "GGGGGGGA", "TTTTTTTA"]], "Duplicate well."),
    ([["", "N1", "AAAAAAAA", "CCCCCCCC", "GGGGGGGG", "TTTTTTTT"]], "Well is missing."),
    ([["A1", "", "AAAAAAAA", "CCCCCCCC", "GGGGGGGG", "TTTTTTTT"]], "Name is missing."),
    ([["A1", "N1", "AAAAAAAA", "CCCCCCCC", "", "TTTTTTTT"]], "Sequence 3 is missing."),
])
def test_atac_validation(
    client: TestClient, session: SyncSession, atac_kit: models.IndexKit, admin_token: str, rows: list, message: str,
):
    before = _barcodes(session, atac_kit)
    response = post_form(client, _path(atac_kit.id), _payload(ATAC_COLUMNS, rows), token=admin_token)

    assert_form_invalid(response, message)
    assert _barcodes(session, atac_kit) == before


# ── Kits of other types ─────────────────────────────────────────────────────


def test_other_kits_are_untouched(
    client: TestClient, session: SyncSession, single_kit: models.IndexKit, dual_kit: models.IndexKit, admin_token: str,
):
    before = _barcodes(session, dual_kit)
    post_form(client, _path(single_kit.id), _payload(SINGLE_COLUMNS, [["B1", "NEW", "ACGTACGT"]]), token=admin_token)
    assert _barcodes(session, dual_kit) == before
