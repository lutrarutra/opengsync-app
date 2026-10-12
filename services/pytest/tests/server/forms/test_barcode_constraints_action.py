"""BarcodeConstraintsAction: check index sequences against the sequencing base constraints.

As legacy ``check_barcode_constraints_workflow`` / ``BarcodeConstraintsForm``: insider-only;
nothing is persisted. Each index position must contain a ``T`` or ``C`` in at least one
of the indices. The form takes i7/i5 sequences (spreadsheet), an optional index kit and
an optional minimum number of samples, and re-renders with the result:

- no sequences, no kit → "Select an index kit or provide some barcodes";
- sequences satisfying the constraints → "Provided sequences satisfy constraints";
- failing sequences without a kit → "... index constraints not met";
- failing sequences (or no sequences) with a kit → suggested kit barcode combinations.
"""

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from .._http import assert_form_invalid, get, post_form, post_form_csrf_mismatch, spreadsheet_payload

PATH = "/htmx/kits/check-barcode-constraints"
COLUMNS = ["Sequence i7", "Sequence i5"]

GOOD_I7, GOOD_I5 = "CCCCCCCC", "TTTTTTTT"   # satisfies the constraints on its own
BAD_I7, BAD_I5 = "AAAAAAAA", "GGGGGGGG"     # never contains T or C

SATISFIED = "Provided sequences satisfy constraints"
NOT_SATISFIED = "Provided sequences do not satisfy constraints"


def _payload(rows: list[tuple[str, str]], kit: models.IndexKit | None = None, min_samples: int | str = "") -> dict[str, str]:
    """As the template's submit script: spreadsheet + columns + kit id + min_samples."""
    return {
        **spreadsheet_payload(COLUMNS, [list(row) for row in rows]),
        "kit": str(kit.id) if kit is not None else "",
        "min_samples": str(min_samples),
    }


def _text(response) -> str:
    """Rendered text without tags (sequences are rendered one <span> per base)."""
    return unescape(re.sub(r"<[^>]+>", "", response.text))


def _num_combinations(response) -> int:
    return len(re.findall(r"<h4>Combination \d+</h4>", response.text))


def _dual_kit(session: SyncSession, wells: dict[str, tuple[str, str]], type=C.IndexType.DUAL_INDEX) -> models.IndexKit:
    """Index kit with one adapter per well; barcodes are named KIT_I7_<well> / KIT_I5_<well>."""
    kit = session.save(Q.index_kit.create(
        name=f"Kit {len(wells)} {id(wells)}", identifier=f"K{id(wells)}"[:12], type=type, supported_protocol_ids=[],
    ), flush=True)
    for well, (seq_i7, seq_i5) in wells.items():
        adapter = session.save(Q.adapter.create(index_kit=kit, well=well), flush=True)
        session.save(Q.barcode.create(name=f"KIT_I7_{well}", sequence=seq_i7, well=well, type=C.BarcodeType.INDEX_I7, adapter=adapter), flush=True)
        session.save(Q.barcode.create(name=f"KIT_I5_{well}", sequence=seq_i5, well=well, type=C.BarcodeType.INDEX_I5, adapter=adapter), flush=True)
    session.commit()
    return kit


def _single_i7_kit(session: SyncSession, wells: dict[str, str]) -> models.IndexKit:
    kit = session.save(Q.index_kit.create(
        name=f"Single {id(wells)}", identifier=f"S{id(wells)}"[:12], type=C.IndexType.SINGLE_INDEX_I7, supported_protocol_ids=[],
    ), flush=True)
    for well, seq_i7 in wells.items():
        adapter = session.save(Q.adapter.create(index_kit=kit, well=well), flush=True)
        session.save(Q.barcode.create(name=f"KIT_I7_{well}", sequence=seq_i7, well=well, type=C.BarcodeType.INDEX_I7, adapter=adapter), flush=True)
    session.commit()
    return kit


@pytest.fixture
def kit(session: SyncSession) -> models.IndexKit:
    """Dual-index kit: A1 fixes any set on its own, B1 never helps."""
    return _dual_kit(session, {"A1": (GOOD_I7, GOOD_I5), "B1": (BAD_I7, BAD_I5)})


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render(client: TestClient, insider_token: str):
    response = get(client, PATH, insider_token)

    assert response.status_code == 200, response.text
    assert "Check Sequencing Index Constraints" in response.text
    for name in ("kit", "min_samples", "csrf_token"):
        assert name in response.text


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_is_denied(client: TestClient, user_token: str):
    assert get(client, PATH, user_token).status_code == 403
    assert post_form(client, PATH, _payload([(GOOD_I7, GOOD_I5)]), token=user_token).status_code == 403


def test_client_with_invalid_submission_is_still_denied(client: TestClient, user_token: str):
    """The role check must not come after validation (which would render the form back)."""
    assert post_form(client, PATH, {"min_samples": "abc"}, token=user_token).status_code == 403


def test_anonymous_is_redirected_to_login(client: TestClient):
    for response in (get(client, PATH), post_form(client, PATH, _payload([(GOOD_I7, GOOD_I5)]))):
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")


def test_csrf_mismatch_is_rejected(client: TestClient, insider_token: str):
    """Nothing is persisted, so rejection means the check is not run."""
    response = post_form_csrf_mismatch(client, PATH, _payload([(GOOD_I7, GOOD_I5)]), token=insider_token)
    assert response.status_code != 200
    assert SATISFIED not in _text(response)


# ── Sequences only ──────────────────────────────────────────────────────────


def test_nothing_provided_asks_for_kit_or_barcodes(client: TestClient, insider_token: str):
    response = post_form(client, PATH, _payload([("", "")]), token=insider_token)

    assert response.status_code in (200, 202)
    assert "Select an index kit or provide some barcodes" in _text(response)


def test_dual_sequences_satisfying_constraints(client: TestClient, insider_token: str):
    response = post_form(client, PATH, _payload([(GOOD_I7, GOOD_I5), (BAD_I7, BAD_I5)]), token=insider_token)

    assert response.status_code == 200, response.text
    text = _text(response)
    assert SATISFIED in text
    assert GOOD_I7 in text and BAD_I5 in text


def test_dual_sequences_failing_constraints_without_kit(client: TestClient, insider_token: str):
    response = post_form(client, PATH, _payload([(BAD_I7, BAD_I5)]), token=insider_token)

    assert response.status_code in (200, 202)
    text = _text(response)
    assert "Index constraints not met. Select another kit." in text
    assert NOT_SATISFIED in text


def test_constraints_are_checked_per_position(client: TestClient, insider_token: str):
    """Together the two indices cover every position with T/C, although neither does alone."""
    response = post_form(client, PATH, _payload([("CACA", "TGTG"), ("ACAC", "GTGT")]), token=insider_token)

    assert response.status_code == 200, response.text
    assert SATISFIED in _text(response)


def test_i7_only_sequences_satisfying_constraints(client: TestClient, insider_token: str):
    response = post_form(client, PATH, _payload([(GOOD_I7, "")]), token=insider_token)

    assert response.status_code == 200, response.text
    assert SATISFIED in _text(response)


def test_i7_only_sequences_failing_constraints_without_kit(client: TestClient, insider_token: str):
    response = post_form(client, PATH, _payload([(BAD_I7, "")]), token=insider_token)

    assert response.status_code in (200, 202)
    text = _text(response)
    assert "i7 index constraints not met" in text
    assert NOT_SATISFIED in text


def test_i5_only_sequences_failing_constraints_without_kit(client: TestClient, insider_token: str):
    response = post_form(client, PATH, _payload([("", BAD_I5)]), token=insider_token)

    assert response.status_code in (200, 202)
    assert "i5 index constraints not met" in _text(response)


def test_i7_sequences_of_different_lengths_are_rejected(client: TestClient, insider_token: str):
    response = post_form(client, PATH, _payload([(GOOD_I7, GOOD_I5), (BAD_I7 + "AA", BAD_I5)]), token=insider_token)

    assert_form_invalid(response, "All i7 index sequences must be the same length")


def test_i5_sequences_of_different_lengths_are_rejected(client: TestClient, insider_token: str):
    response = post_form(client, PATH, _payload([(GOOD_I7, GOOD_I5), (BAD_I7, BAD_I5 + "GG")]), token=insider_token)

    assert_form_invalid(response, "All i5 index sequences must be the same length")


def test_missing_i5_for_some_rows_is_rejected(client: TestClient, insider_token: str):
    """A missing i5 is caught as a length mismatch (legacy never reached its count check)."""
    response = post_form(client, PATH, _payload([(GOOD_I7, GOOD_I5), (BAD_I7, "")]), token=insider_token)

    assert_form_invalid(response, "All i5 index sequences must be the same length")


def test_invalid_min_samples_is_rejected(client: TestClient, insider_token: str):
    response = post_form(client, PATH, _payload([(GOOD_I7, GOOD_I5)], min_samples="abc"), token=insider_token)
    assert_form_invalid(response)


# ── With a kit ──────────────────────────────────────────────────────────────


def test_kit_only_suggests_valid_combinations(client: TestClient, kit: models.IndexKit, insider_token: str):
    """With no sequences, combinations of kit barcodes that satisfy the constraints are suggested."""
    response = post_form(client, PATH, _payload([("", "")], kit=kit), token=insider_token)

    assert response.status_code == 200, response.text
    text = _text(response)
    for expected in ("KIT_I7_A1", "KIT_I5_A1", "A1", GOOD_I7, GOOD_I5):
        assert expected in text
    # (A1), (A1, B1), (B1, A1); (B1) alone is not valid.
    assert _num_combinations(response) == 3


def test_min_samples_limits_suggestion_size(client: TestClient, kit: models.IndexKit, insider_token: str):
    response = post_form(client, PATH, _payload([("", "")], kit=kit, min_samples=2), token=insider_token)

    assert response.status_code == 200, response.text
    # Only the two-barcode combinations remain.
    assert _num_combinations(response) == 2


def test_failing_dual_sequences_get_kit_suggestions(client: TestClient, kit: models.IndexKit, insider_token: str):
    response = post_form(client, PATH, _payload([(BAD_I7, BAD_I5)], kit=kit), token=insider_token)

    assert response.status_code == 200, response.text
    text = _text(response)
    assert "Index constraints not met" not in text
    assert "KIT_I7_A1" in text and "KIT_I5_A1" in text
    # The user's own sequences are listed with each suggestion.
    assert BAD_I7 in text and BAD_I5 in text
    assert _num_combinations(response) == 3


def test_satisfying_dual_sequences_with_kit_need_no_suggestions(client: TestClient, kit: models.IndexKit, insider_token: str):
    response = post_form(client, PATH, _payload([(GOOD_I7, GOOD_I5)], kit=kit), token=insider_token)

    assert response.status_code == 200, response.text
    assert SATISFIED in _text(response)
    assert _num_combinations(response) == 0


def test_failing_i7_sequences_get_kit_i7_suggestions(client: TestClient, kit: models.IndexKit, insider_token: str):
    response = post_form(client, PATH, _payload([(BAD_I7, "")], kit=kit), token=insider_token)

    assert response.status_code == 200, response.text
    text = _text(response)
    assert "KIT_I7_A1" in text
    assert "KIT_I5_A1" not in text


def test_failing_i5_sequences_get_kit_i5_suggestions(client: TestClient, kit: models.IndexKit, insider_token: str):
    response = post_form(client, PATH, _payload([("", BAD_I5)], kit=kit), token=insider_token)

    assert response.status_code == 200, response.text
    text = _text(response)
    assert "KIT_I5_A1" in text
    assert "KIT_I7_A1" not in text


def test_single_index_kit_suggests_i7_barcodes(client: TestClient, session: SyncSession, insider_token: str):
    """Single-index i7 kits are offered by the kit search, so they must be usable for i7-only checks."""
    single = _single_i7_kit(session, {"A1": GOOD_I7, "B1": BAD_I7})

    response = post_form(client, PATH, _payload([(BAD_I7, "")], kit=single), token=insider_token)

    assert response.status_code == 200, response.text
    assert "KIT_I7_A1" in _text(response)


def test_dual_sequences_with_single_index_kit_are_rejected(client: TestClient, session: SyncSession, insider_token: str):
    single = _single_i7_kit(session, {"A1": GOOD_I7})

    response = post_form(client, PATH, _payload([(BAD_I7, BAD_I5)], kit=single), token=insider_token)

    assert response.status_code in (200, 202)
    assert "is not a dual index kit" in _text(response)


def test_atac_kit_is_rejected(client: TestClient, session: SyncSession, insider_token: str):
    atac = session.save(Q.index_kit.create(
        name="ATAC kit", identifier="ATAC_K", type=C.IndexType.TENX_ATAC_INDEX, supported_protocol_ids=[],
    ), flush=True)
    session.commit()

    response = post_form(client, PATH, _payload([(BAD_I7, BAD_I5)], kit=atac), token=insider_token)

    assert_form_invalid(response, "10x ATAC index kits are not supported")


def test_kit_with_mixed_i7_lengths_is_rejected(client: TestClient, session: SyncSession, insider_token: str):
    mixed = _dual_kit(session, {"A1": (GOOD_I7, GOOD_I5), "B1": (BAD_I7 + "AA", BAD_I5)})

    response = post_form(client, PATH, _payload([(BAD_I7, BAD_I5)], kit=mixed), token=insider_token)

    assert_form_invalid(response, "has i7 index sequences of different lengths")


def test_unknown_kit_is_404(client: TestClient, insider_token: str):
    payload = {**_payload([(BAD_I7, BAD_I5)]), "kit": "999999"}
    assert post_form(client, PATH, payload, token=insider_token).status_code == 404
