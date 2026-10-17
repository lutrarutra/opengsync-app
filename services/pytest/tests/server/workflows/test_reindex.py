"""ReindexWorkflow: replace the barcodes (indices) of selected libraries.

As legacy ``reindex_workflow``: the context is a sequencing request (WRITE needed), a lab
prep or pool (insider), or none (insider). Steps: select libraries → barcode input (i7/i5,
from a kit by well/name or custom sequences) → 10X ATAC input (four sequences) when ATAC
libraries are selected → barcode match when no kit was given (pick a kit the sequences
match, or Custom with orientation + primer) → completion, which replaces each library's
indices and index type and redirects to the context.

Custom orientation options are covered in ``test_reindex_barcode_match.py``, the prep-table
prefill in ``test_reindex_prep_table_prefill.py``.
"""

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_lab_prep, create_library, create_seq_request
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch, spreadsheet_payload
from .library_annotation._workflow import create_dual_index_kit, create_tenx_atac_index_kit

BARCODE_COLUMNS = ["Library", "Index Well", "i7 Kit", "i7 Name", "i7 Sequence", "i5 Kit", "i5 Name", "i5 Sequence"]
ATAC_COLUMNS = ["Library", "Index Well", "Kit", "Name", "Sequence 1", "Sequence 2", "Sequence 3", "Sequence 4"]
PRIMER = "AATGATACGGCGACCACCGA"

KIT_WELLS = {
    "A1": ("D701", "ATTACTCG", "D501", "TATAGCCT"),
    "B1": ("D702", "TCCGGAGA", "D502", "ATAGAGGC"),
}
ATAC_SEQUENCES = ["AAACGGCG", "CCTACCAT", "GGCGTTTC", "TTGTAAGA"]


def _url(client: TestClient, route: str) -> str:
    return client.app.url_path_for(f"ReindexWorkflow.{route}")  # type: ignore[attr-defined]


def _label(library: models.Library) -> str:
    return f"{library.name} [{library.id}]"


def _kit_label(kit: models.IndexKit) -> str:
    return f"[{kit.identifier}] {kit.name}"


def _indices(session: SyncSession, library: models.Library) -> list[tuple]:
    session.expire_all()
    library = session.get_one(Q.library.select(id=library.id))
    return sorted(
        (i.name_i7, i.sequence_i7, i.name_i5, i.sequence_i5, i.index_kit_i7_id, i.orientation)
        for i in library.indices
    )


def _index_type(session: SyncSession, library: models.Library):
    session.expire_all()
    return session.get_one(Q.library.select(id=library.id)).index_type


class Run:
    """A reindex run in the context of a draft request owned by ``user``."""

    def __init__(self, session: SyncSession, user: models.User):
        self.seq_request = create_seq_request(session, user)
        self.a = create_library(session, user, self.seq_request)
        self.b = create_library(session, user, self.seq_request)
        self.a.indices.append(models.LibraryIndex(name_i7="OLD", sequence_i7="GGGGGGGG"))
        session.save(self.a, flush=True)
        session.commit()
        self.params: dict[str, Any] = {"uuid": str(uuid.uuid4()), "seq_request_id": self.seq_request.id}

    def select(self, client: TestClient, token: str, libraries: list[models.Library]):
        return post_form(
            client, _url(client, "SelectSamplesForm.Submit"),
            {"selected_library_ids": json.dumps([lib.id for lib in libraries])}, token=token, params=self.params,
        )

    def barcodes(self, client: TestClient, token: str, rows: list[list[Any]]):
        return post_form(client, _url(client, "BarcodeInputForm.Submit"), spreadsheet_payload(BARCODE_COLUMNS, rows), token=token, params=self.params)

    def atac(self, client: TestClient, token: str, rows: list[list[Any]]):
        return post_form(client, _url(client, "TENXATACBarcodeInputForm.Submit"), spreadsheet_payload(ATAC_COLUMNS, rows), token=token, params=self.params)

    def match(self, client: TestClient, token: str, data: dict[str, str]):
        return post_form(client, _url(client, "BarcodeMatchForm.Submit"), data, token=token, params=self.params)

    def complete(self, client: TestClient, token: str):
        return post_form(client, _url(client, "CompleteReindexForm.Submit"), {}, token=token, params=self.params)


@pytest.fixture
def run(session: SyncSession, user) -> Run:
    return Run(session, user)


@pytest.fixture
def kit(session: SyncSession) -> models.IndexKit:
    return create_dual_index_kit(session, "RIDX_KIT", "Reindex Dual Kit", KIT_WELLS)


def _kit_rows(run: Run, kit: models.IndexKit) -> list[list[Any]]:
    return [
        [_label(run.a), "A1", _kit_label(kit), "", "", "", "", ""],
        [_label(run.b), "B01", _kit_label(kit), "", "", "", "", ""],
    ]


# ── Begin and access ────────────────────────────────────────────────────────


def test_owner_can_begin_on_draft_request(client: TestClient, run: Run, user_token: str):
    response = get(client, _url(client, "Begin"), user_token, params=run.params)
    assert response.status_code == 200, response.text


def test_other_users_request_is_denied(client: TestClient, run: Run, user_2_token: str):
    assert get(client, _url(client, "Begin"), user_2_token, params=run.params).status_code == 403
    assert run.select(client, user_2_token, [run.a]).status_code == 403


def test_owner_cannot_reindex_submitted_request(client: TestClient, session: SyncSession, run: Run, user_token: str, insider_token: str):
    run.seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.save(run.seq_request, flush=True)
    session.commit()

    assert get(client, _url(client, "Begin"), user_token, params=run.params).status_code == 403
    assert get(client, _url(client, "Begin"), insider_token, params=run.params).status_code == 200


def test_lab_prep_and_no_context_are_insider_only(
    client: TestClient, session: SyncSession, insider, user_token: str, insider_token: str,
):
    lab_prep = create_lab_prep(session, insider)
    session.commit()
    for params in ({"lab_prep_id": lab_prep.id}, {}):
        assert get(client, _url(client, "Begin"), user_token, params=params).status_code == 403
        assert get(client, _url(client, "Begin"), insider_token, params=params).status_code == 200


@pytest.mark.parametrize("param", ["seq_request_id", "lab_prep_id", "pool_id"])
def test_unknown_context_is_404(client: TestClient, insider_token: str, param: str):
    assert get(client, _url(client, "Begin"), insider_token, params={param: 999999}).status_code == 404


def test_anonymous_is_redirected_to_login(client: TestClient, run: Run):
    response = get(client, _url(client, "Begin"), params=run.params)
    assert response.status_code == 303
    assert "/auth/login" in response.headers.get("location", "")


def test_csrf_mismatch_is_rejected(client: TestClient, run: Run, user_token: str):
    response = post_form_csrf_mismatch(
        client, _url(client, "SelectSamplesForm.Submit"), {"selected_library_ids": json.dumps([run.a.id])},
        token=user_token, params=run.params,
    )
    assert response.status_code != 200


# ── Select ──────────────────────────────────────────────────────────────────


def test_select_libraries_shows_barcode_input(client: TestClient, run: Run, user_token: str):
    response = run.select(client, user_token, [run.a, run.b])

    assert response.status_code == 200, response.text
    assert _url(client, "BarcodeInputForm.Submit") in response.text
    assert _label(run.a) in response.text and _label(run.b) in response.text
    assert "GGGGGGGG" in response.text  # current index is prefilled


def test_empty_selection_is_rejected(client: TestClient, run: Run, user_token: str):
    response = post_form(client, _url(client, "SelectSamplesForm.Submit"), {"selected_library_ids": "[]"}, token=user_token, params=run.params)
    assert_form_invalid(response)


def test_library_outside_context_is_404(client: TestClient, session: SyncSession, run: Run, user, user_token: str):
    other = create_library(session, user, create_seq_request(session, user))
    session.commit()

    assert run.select(client, user_token, [run.a, other]).status_code == 404


# ── Barcode input from a kit ────────────────────────────────────────────────


def test_kit_barcodes_skip_match_and_complete(
    client: TestClient, session: SyncSession, run: Run, kit: models.IndexKit, user_token: str,
):
    run.select(client, user_token, [run.a, run.b])
    response = run.barcodes(client, user_token, _kit_rows(run, kit))

    assert response.status_code == 200, response.text
    assert _url(client, "CompleteReindexForm.Submit") in response.text

    response = run.complete(client, user_token)

    assert_htmx_redirect(response, f"/seq_requests/{run.seq_request.id}")
    assert_flash(response, "Libraries Re-Indexed!", category="success")
    forward = C.BarcodeOrientation.FORWARD
    assert _indices(session, run.a) == [("D701", "ATTACTCG", "D501", "TATAGCCT", kit.id, forward)]
    assert _indices(session, run.b) == [("D702", "TCCGGAGA", "D502", "ATAGAGGC", kit.id, forward)]
    assert _index_type(session, run.a) == C.IndexType.DUAL_INDEX


def test_kit_barcode_by_name(client: TestClient, session: SyncSession, run: Run, kit: models.IndexKit, user_token: str):
    run.select(client, user_token, [run.a])
    # Dual kit: an empty i5 name takes the i7 name (as legacy), so kits with distinct i5 names need both
    run.barcodes(client, user_token, [[_label(run.a), "", _kit_label(kit), "D702", "", "", "D502", ""]])
    run.complete(client, user_token)

    assert [(i[0], i[1], i[2]) for i in _indices(session, run.a)] == [("D702", "TCCGGAGA", "D502")]


@pytest.mark.parametrize("row, message", [
    (["", "H12", "KIT", "", "", "", "", ""], "i7 well 'H12' not found in kit"),
    (["", "", "KIT", "D799", "", "", "", ""], "i7 name 'D799' not found in kit"),
    (["", "", "KIT", "", "", "", "", ""], "'index_well' or 'name_i7' must be defined when kit is defined"),
    (["", "", "", "", "", "", "", ""], "missing kit/name or sequence_i7"),
    (["", "", "", "custom", "ACGTXACG", "", "", ""], "Invalid base(s) 'X'"),
])
def test_invalid_barcode_input_is_rejected(
    client: TestClient, session: SyncSession, run: Run, kit: models.IndexKit, user_token: str, row: list, message: str,
):
    run.select(client, user_token, [run.a])
    row = [_label(run.a) if i == 0 else (_kit_label(kit) if cell == "KIT" else cell) for i, cell in enumerate(row)]

    response = run.barcodes(client, user_token, [row])

    assert_form_invalid(response, message)
    assert _indices(session, run.a) == [("OLD", "GGGGGGGG", None, None, None, None)]


def test_every_selected_library_must_be_listed(client: TestClient, run: Run, kit: models.IndexKit, user_token: str):
    run.select(client, user_token, [run.a, run.b])

    response = run.barcodes(client, user_token, [[_label(run.a), "A1", _kit_label(kit), "", "", "", "", ""]])

    assert_form_invalid(response, f"Each selected library must be listed at least once. Missing: {run.b.name} [{run.b.id}]")


def test_unselected_library_cannot_be_added(client: TestClient, session: SyncSession, run: Run, kit: models.IndexKit, user_token: str):
    run.select(client, user_token, [run.a])

    response = run.barcodes(client, user_token, [
        [_label(run.a), "A1", _kit_label(kit), "", "", "", "", ""],
        [_label(run.b), "B1", _kit_label(kit), "", "", "", "", ""],
    ])

    assert_form_invalid(response, f"Invalid value '{_label(run.b)}' for 'Library'.")


def test_unparseable_library_cell_is_rejected(client: TestClient, run: Run, kit: models.IndexKit, user_token: str):
    run.select(client, user_token, [run.a])

    response = run.barcodes(client, user_token, [
        [_label(run.a), "A1", _kit_label(kit), "", "", "", "", ""],
        ["not a library", "B1", _kit_label(kit), "", "", "", "", ""],
    ])

    assert_form_invalid(response, "Invalid value 'not a library' for 'Library'.")


def test_several_indices_per_library(client: TestClient, session: SyncSession, run: Run, kit: models.IndexKit, user_token: str):
    run.select(client, user_token, [run.a])
    run.barcodes(client, user_token, [
        [_label(run.a), "A1", _kit_label(kit), "", "", "", "", ""],
        [_label(run.a), "B1", _kit_label(kit), "", "", "", "", ""],
    ])
    run.complete(client, user_token)

    assert [i[0] for i in _indices(session, run.a)] == ["D701", "D702"]


def test_del_removes_indices(client: TestClient, session: SyncSession, run: Run, user_token: str):
    """Index well 'del' drops the row: the library ends up without indices."""
    run.select(client, user_token, [run.a])
    response = run.barcodes(client, user_token, [[_label(run.a), "del", "", "", "GGGGGGGG", "", "", ""]])
    assert response.status_code == 200, response.text
    run.complete(client, user_token)

    assert _indices(session, run.a) == []


# ── Barcode match ───────────────────────────────────────────────────────────


def test_custom_sequences_of_a_known_kit_offer_it_in_match(
    client: TestClient, session: SyncSession, run: Run, kit: models.IndexKit, user_token: str,
):
    run.select(client, user_token, [run.a])
    response = run.barcodes(client, user_token, [[_label(run.a), "", "", "", "ATTACTCG", "", "", "TATAGCCT"]])

    assert response.status_code == 200, response.text
    assert _url(client, "BarcodeMatchForm.Submit") in response.text
    assert _kit_label(kit) in response.text

    response = run.match(client, user_token, {"i7_kit": str(kit.id), "i5_kit": str(kit.id)})
    assert response.status_code == 200, response.text
    run.complete(client, user_token)

    assert _indices(session, run.a) == [("D701", "ATTACTCG", "D501", "TATAGCCT", kit.id, C.BarcodeOrientation.FORWARD)]


def test_custom_primer_is_added_as_request_comment(client: TestClient, session: SyncSession, run: Run, user_token: str):
    run.select(client, user_token, [run.a])
    run.barcodes(client, user_token, [[_label(run.a), "", "", "custom", "ACGTACGTAA", "", "", ""]])
    run.match(client, user_token, {"i7_kit": "0", "i7_option": "forward", "i7_primer": PRIMER})
    run.complete(client, user_token)

    session.expire_all()
    seq_request = session.get_one(Q.seq_request.select(id=run.seq_request.id))
    assert [c.text for c in seq_request.comments] == [f"i7 Primer Sequence: {PRIMER}"]


# ── 10X ATAC ────────────────────────────────────────────────────────────────


@pytest.fixture
def atac(session: SyncSession, run: Run, user) -> models.Library:
    library = create_library(session, user, run.seq_request)
    library.type = C.LibraryType.TENX_SC_ATAC
    session.save(library, flush=True)
    session.commit()
    return library


def test_atac_only_selection_goes_to_atac_input(client: TestClient, session: SyncSession, run: Run, atac: models.Library, user_token: str):
    response = run.select(client, user_token, [atac])

    assert response.status_code == 200, response.text
    assert _url(client, "TENXATACBarcodeInputForm.Submit") in response.text

    response = run.atac(client, user_token, [[_label(atac), "", "", "SI-NA-A1", *ATAC_SEQUENCES]])
    assert response.status_code == 200, response.text
    assert_htmx_redirect(run.complete(client, user_token), f"/seq_requests/{run.seq_request.id}")

    assert sorted(i[1] for i in _indices(session, atac)) == ATAC_SEQUENCES
    assert _index_type(session, atac) == C.IndexType.TENX_ATAC_INDEX


def test_mixed_selection_asks_standard_then_atac(
    client: TestClient, session: SyncSession, run: Run, atac: models.Library, kit: models.IndexKit, user_token: str,
):
    run.select(client, user_token, [run.a, atac])
    response = run.barcodes(client, user_token, [[_label(run.a), "A1", _kit_label(kit), "", "", "", "", ""]])

    assert response.status_code == 200, response.text
    assert _url(client, "TENXATACBarcodeInputForm.Submit") in response.text

    run.atac(client, user_token, [[_label(atac), "", "", "SI-NA-A1", *ATAC_SEQUENCES]])
    run.complete(client, user_token)

    assert [i[0] for i in _indices(session, run.a)] == ["D701"]
    assert len(_indices(session, atac)) == 4


def test_atac_kit_barcodes(client: TestClient, session: SyncSession, run: Run, atac: models.Library, user_token: str):
    atac_kit = create_tenx_atac_index_kit(session, "RIDX_ATAC", "Reindex ATAC Kit", {"A1": ("SI-NA-A1", ATAC_SEQUENCES)})
    run.select(client, user_token, [atac])

    response = run.atac(client, user_token, [[_label(atac), "", _kit_label(atac_kit), "SI-NA-A1", *ATAC_SEQUENCES]])
    assert response.status_code == 200, response.text
    run.complete(client, user_token)

    assert {i[4] for i in _indices(session, atac)} == {atac_kit.id}


def test_atac_missing_sequence_is_rejected(client: TestClient, run: Run, atac: models.Library, user_token: str):
    run.select(client, user_token, [atac])

    response = run.atac(client, user_token, [[_label(atac), "", "", "SI-NA-A1", *ATAC_SEQUENCES[:3], ""]])

    assert_form_invalid(response, "missing 'Sequence 1/2/3/4' or 'Name' + 'Kit' or 'Index Well' + 'Kit'")


def test_atac_kit_well_fills_sequences(client: TestClient, session: SyncSession, run: Run, atac: models.Library, user_token: str):
    atac_kit = create_tenx_atac_index_kit(session, "RIDX_ATAC", "Reindex ATAC Kit", {"A1": ("SI-NA-A1", ATAC_SEQUENCES)})
    run.select(client, user_token, [atac])

    response = run.atac(client, user_token, [[_label(atac), "A01", _kit_label(atac_kit), "", "", "", "", ""]])
    assert response.status_code == 200, response.text
    run.complete(client, user_token)

    assert sorted((i[0], i[1], i[4]) for i in _indices(session, atac)) == [("SI-NA-A1", s, atac_kit.id) for s in sorted(ATAC_SEQUENCES)]


def test_atac_unknown_kit_well_is_rejected(client: TestClient, session: SyncSession, run: Run, atac: models.Library, user_token: str):
    atac_kit = create_tenx_atac_index_kit(session, "RIDX_ATAC", "Reindex ATAC Kit", {"A1": ("SI-NA-A1", ATAC_SEQUENCES)})
    run.select(client, user_token, [atac])

    response = run.atac(client, user_token, [[_label(atac), "H12", _kit_label(atac_kit), "", "", "", "", ""]])

    assert_form_invalid(response, "'H12' not found in kit")


# ── Navigation and state ────────────────────────────────────────────────────


def test_back_navigation_keeps_barcodes(client: TestClient, run: Run, kit: models.IndexKit, user_token: str):
    run.select(client, user_token, [run.a, run.b])
    run.barcodes(client, user_token, _kit_rows(run, kit))

    response = get(client, _url(client, "BarcodeInputForm.Previous"), user_token, params=run.params)
    assert response.status_code == 200, response.text
    assert "TCCGGAGA" in response.text  # B1 resolved from the kit

    response = get(client, _url(client, "SelectSamplesForm.Previous"), user_token, params=run.params)
    assert response.status_code == 200, response.text


def test_completion_redirects_to_lab_prep(
    client: TestClient, session: SyncSession, run: Run, insider, kit: models.IndexKit, insider_token: str,
):
    lab_prep = create_lab_prep(session, insider)
    run.a.lab_prep_id = lab_prep.id
    session.save(run.a, flush=True)
    session.commit()
    run.params = {"uuid": str(uuid.uuid4()), "lab_prep_id": lab_prep.id}

    run.select(client, insider_token, [run.a])
    run.barcodes(client, insider_token, [[_label(run.a), "A1", _kit_label(kit), "", "", "", "", ""]])

    assert_htmx_redirect(run.complete(client, insider_token), f"/lab_preps/{lab_prep.id}")


def test_completion_clears_state(client: TestClient, run: Run, kit: models.IndexKit, user_token: str):
    run.select(client, user_token, [run.a])
    run.barcodes(client, user_token, [[_label(run.a), "A1", _kit_label(kit), "", "", "", "", ""]])
    run.complete(client, user_token)

    r = Redis(connection_pool=client.app.state.redis_pool)  # type: ignore[attr-defined]
    assert list(r.scan_iter(f"ReindexWorkflow:{run.params['uuid']}:*")) == []


def test_replayed_completion_is_400(client: TestClient, session: SyncSession, run: Run, kit: models.IndexKit, user_token: str):
    run.select(client, user_token, [run.a])
    run.barcodes(client, user_token, [[_label(run.a), "A1", _kit_label(kit), "", "", "", "", ""]])
    run.complete(client, user_token)
    before = _indices(session, run.a)

    assert run.complete(client, user_token).status_code == 400
    assert _indices(session, run.a) == before


@pytest.mark.parametrize("route", ["BarcodeInputForm.Previous", "BarcodeMatchForm.Previous", "CompleteReindexForm.Previous"])
def test_later_step_without_state_is_400(client: TestClient, run: Run, user_token: str, route: str):
    assert get(client, _url(client, route), user_token, params=run.params).status_code == 400


def test_run_cannot_switch_to_another_request(
    client: TestClient, session: SyncSession, run: Run, user, kit: models.IndexKit, user_token: str,
):
    """State is per UUID: a run started for one request must not be completed under another."""
    run.select(client, user_token, [run.a])
    run.barcodes(client, user_token, [[_label(run.a), "A1", _kit_label(kit), "", "", "", "", ""]])

    other_request = create_seq_request(session, user)
    session.commit()
    run.params["seq_request_id"] = other_request.id

    assert run.complete(client, user_token).status_code == 400
    assert _indices(session, run.a) == [("OLD", "GGGGGGGG", None, None, None, None)]
