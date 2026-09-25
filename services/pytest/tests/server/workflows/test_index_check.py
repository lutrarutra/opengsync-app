"""Tests for IndexCheckWorkflow — barcode orientation validation workflow."""

import ast
import html
import json
import re
import uuid as uuid_mod

import pytest
from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import (
    create_user, create_seq_request, create_library, create_index_kit,
)
from .._http import (
    OpenGSyncTestClient, assert_htmx_redirect, assert_form_invalid,
    get, post_form, flush_redis, spreadsheet_payload,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _add_index(
    session: SyncSession,
    library: models.Library,
    sequence_i7: str = "ACGTACGT",
    sequence_i5: str | None = None,
    orientation: C.BarcodeOrientation | None = C.BarcodeOrientation.FORWARD_NOT_VALIDATED,
    index_kit_i7: models.IndexKit | None = None,
    index_kit_i5: models.IndexKit | None = None,
    name_i7: str | None = None,
    name_i5: str | None = None,
) -> models.LibraryIndex:
    index = Q.library_index.create(
        library_id=library.id,
        name_i7=name_i7 or "i7_index",
        name_i5=name_i5 or ("i5_index" if sequence_i5 else None),
        sequence_i7=sequence_i7,
        sequence_i5=sequence_i5,
        index_kit_i7_id=index_kit_i7.id if index_kit_i7 else None,
        index_kit_i5_id=index_kit_i5.id if index_kit_i5 else None,
        orientation=orientation,
    )
    session.save(index, flush=True)
    # Ensure the library's indices relationship is refreshed
    session.refresh(library)
    return index


PREFIX = "/htmx/workflows/index-check"
CSRF = "test-csrf"

VERIFY_COLUMNS = ["Library [Index ID]", "Orientation", "i7 Name", "i7 Sequence", "i5 Name", "i5 Sequence"]
ORIENTATION_LABELS = {"forward": "Forward", "reverse_complement": "Reverse Complement"}


def _verify_rows(verify_page) -> list[list]:
    """Rows rendered into the verify-orientations spreadsheet."""
    match = re.search(r"data: (\[.*?\]),\s*columns:", verify_page.text, re.DOTALL)
    assert match is not None, "verify-orientations spreadsheet not found"
    return ast.literal_eval(match.group(1))


def _verify_payload(verify_page, orientations: list[str]) -> dict[str, str]:
    """Set the orientation of each rendered row and submit the spreadsheet like the browser does."""
    rows = _verify_rows(verify_page)
    assert len(rows) == len(orientations)
    for row, orientation in zip(rows, orientations):
        row[1] = ORIENTATION_LABELS[orientation]
    return spreadsheet_payload(VERIFY_COLUMNS, rows)


# ── Phase A: Workflow step navigation ────────────────────────────────────────

class TestIndexCheckBegin:
    def test_index_check_begin(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """GET /htmx/workflows/index-check/begin with seq_request_id returns 200."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib)
        session.commit()

        response = get(
            client, f"{PREFIX}/begin", insider_token,
            params={"seq_request_id": sr.id},
            htmx=True,
        )
        assert response.status_code == 200
        assert "select-libraries" in response.text or "Check Index" in response.text

    def test_index_check_begin_insider_only(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        user: models.User,
        user_token: str,
    ):
        """Non-insider user gets 403 when accessing workflow."""
        sr = create_seq_request(session, user)
        session.commit()

        response = get(
            client, f"{PREFIX}/begin", user_token,
            params={"seq_request_id": sr.id},
        )
        assert response.status_code == 403


class TestIndexCheckWorkflowCard:
    def test_workflows_tab_shows_index_check_to_insiders(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        user: models.User,
        user_token: str,
        insider: models.User,
        insider_token: str,
    ):
        """The Workflows tab offers Check Index Orientations to insiders for library submissions only."""
        pooled = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
        raw = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
        session.commit()

        def page(seq_request: models.SeqRequest, token: str) -> str:
            response = get(client, f"/seq_requests/{seq_request.id}", token)
            assert response.status_code == 200
            return response.text

        assert "index-check/begin" in page(pooled, insider_token)
        assert "index-check/begin" not in page(raw, insider_token)
        assert "index-check/begin" not in page(pooled, user_token)


class TestIndexCheckSelectLibrariesSubmit:
    def test_index_check_select_libraries_submit(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """POST select-libraries stores library_table and barcode_table in workflow.tables."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        idx = _add_index(session, lib)
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        # First GET to initialize the workflow
        get(client, f"{PREFIX}/begin", insider_token, params=params, htmx=True)

        # Now submit the form with selected library
        response = post_form(
            client,
            f"{PREFIX}/select-libraries",
            {"selected_library_ids": json.dumps([lib.id])},
            token=insider_token,
            params=params,
        )
        assert response.status_code == 200
        assert "verify" in response.text.lower() or "orientation" in response.text.lower()


class TestIndexCheckVerifyOrientationsSubmit:
    def test_index_check_verify_orientations_submit(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """POST verify-orientations stores orientation metadata."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib)
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        # Navigate through steps
        get(client, f"{PREFIX}/begin", insider_token, params=params, htmx=True)
        verify_page = post_form(
            client, f"{PREFIX}/select-libraries",
            {"selected_library_ids": json.dumps([lib.id])},
            token=insider_token, params=params,
        )

        # Submit verification with forward orientation
        response = post_form(
            client,
            f"{PREFIX}/verify-orientations",
            _verify_payload(verify_page, ["forward"]),
            token=insider_token,
            params=params,
        )
        assert response.status_code == 200
        assert "complete" in response.text.lower() or "summary" in response.text.lower()


class TestIndexCheckCompleteSubmit:
    def test_index_check_complete_submit(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """POST complete updates DB and redirects."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        idx = _add_index(session, lib, sequence_i7="ACGTACGT")
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        get(client, f"{PREFIX}/begin", insider_token, params=params, htmx=True)
        verify_page = post_form(
            client, f"{PREFIX}/select-libraries",
            {"selected_library_ids": json.dumps([lib.id])},
            token=insider_token, params=params,
        )
        post_form(
            client, f"{PREFIX}/verify-orientations",
            _verify_payload(verify_page, ["forward"]),
            token=insider_token, params=params,
        )

        # Submit completion
        response = post_form(
            client, f"{PREFIX}/complete-index-check",
            {},
            token=insider_token,
            params=params,
        )
        assert_htmx_redirect(response, f"/seq_requests/{sr.id}")

        # Verify DB was updated
        session.expire_all()
        updated_idx = session.get_one(Q.library_index.select(id=idx.id))
        assert updated_idx.orientation == C.BarcodeOrientation.FORWARD


# ── Phase B: Library filtering ───────────────────────────────────────────────

class TestSelectLibrariesFilters:
    def test_select_libraries_filters_unvalidated_only(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Only unvalidated libraries appear in pre-filtered selection."""
        sr = create_seq_request(session, insider)
        lib_validated = create_library(session, insider, sr)
        lib_unvalidated = create_library(session, insider, sr)
        _add_index(session, lib_validated, orientation=C.BarcodeOrientation.FORWARD)
        _add_index(session, lib_unvalidated, orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED)
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        response = get(
            client, f"{PREFIX}/begin", insider_token,
            params=params, htmx=True,
        )
        assert response.status_code == 200

    def test_select_libraries_table_filters_unvalidated(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """The select step's library table lists only libraries with unvalidated or unset orientations."""
        sr = create_seq_request(session, insider)
        lib_forward = create_library(session, insider, sr)
        lib_unvalidated = create_library(session, insider, sr)
        lib_unset = create_library(session, insider, sr)
        _add_index(session, lib_forward, orientation=C.BarcodeOrientation.FORWARD)
        _add_index(session, lib_unvalidated, orientation=C.BarcodeOrientation.REVERSE_COMPLEMENT_NOT_VALIDATED)
        _add_index(session, lib_unset, orientation=None)
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}
        response = get(client, f"{PREFIX}/begin", insider_token, params=params, htmx=True)
        assert response.status_code == 200

        # Load the table the same way the page does, with the step's preset filter
        match = re.search(r'hx-get="([^"]*render-table-page[^"]*)"', response.text)
        assert match is not None
        response = get(client, html.unescape(match.group(1)), insider_token, htmx=True)
        assert response.status_code == 200
        assert f'id="library-row-{lib_unvalidated.id}"' in response.text
        assert f'id="library-row-{lib_unset.id}"' in response.text
        assert f'id="library-row-{lib_forward.id}"' not in response.text
        # "Not set" can be selected in the orientation dropdown
        assert 'data-value="null"' in response.text

    def test_select_libraries_all_validated(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """All libraries already validated — workflow shows empty selection gracefully."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, orientation=C.BarcodeOrientation.FORWARD)
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        response = get(
            client, f"{PREFIX}/begin", insider_token,
            params=params, htmx=True,
        )
        assert response.status_code == 200

    def test_select_libraries_no_indices(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Libraries without indices are excluded from selection."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)  # no indices
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        response = get(
            client, f"{PREFIX}/begin", insider_token,
            params=params, htmx=True,
        )
        assert response.status_code == 200


# ── Phase C: Orientation verification ────────────────────────────────────────

class TestVerifyOrientations:
    def _navigate_to_verify(
        self, client, insider_token, params, library_ids, session
    ):
        """Helper: navigate from begin through select-libraries to verify-orientations."""
        get(client, f"{PREFIX}/begin", insider_token, params=params, htmx=True)
        return post_form(
            client, f"{PREFIX}/select-libraries",
            {"selected_library_ids": json.dumps(library_ids)},
            token=insider_token, params=params,
        )

    def _complete_workflow(
        self, client, insider_token, params, verify_page, orientations
    ):
        """Helper: submit the orientations on the verify page, then complete the workflow."""
        post_form(
            client, f"{PREFIX}/verify-orientations",
            _verify_payload(verify_page, orientations),
            token=insider_token, params=params,
        )
        return post_form(
            client, f"{PREFIX}/complete-index-check",
            {},
            token=insider_token, params=params,
        )

    def test_verify_kit_index_auto_forward(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Kit-matched index auto-sets to FORWARD."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        kit = create_index_kit(session)
        _add_index(
            session, lib,
            sequence_i7="ACGTACGT",
            index_kit_i7=kit,
            name_i7="i7_index",
            orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED,
        )
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)

        response = self._complete_workflow(
            client, insider_token, params, verify_page, ["forward"]
        )
        assert response.status_code in (200, 204)

    def test_verify_custom_index_forward(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Custom index with Forward selection keeps sequence, sets FORWARD."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, sequence_i7="ACGTACGT")
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)

        response = self._complete_workflow(
            client, insider_token, params, verify_page, ["forward"]
        )
        assert response.status_code in (200, 204)

    def test_verify_custom_index_reverse_complement(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Custom index with RC selection reverse-complements sequence and sets FORWARD."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        original_seq = "ACGTACGT"
        idx = _add_index(session, lib, sequence_i7=original_seq)
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)

        response = self._complete_workflow(
            client, insider_token, params, verify_page, ["reverse_complement"]
        )
        assert response.status_code in (200, 204)

        session.expire_all()
        updated_idx = session.get_one(Q.library_index.select(id=idx.id))
        expected_rc = models.Barcode.reverse_complement(original_seq)
        assert updated_idx.sequence_i7 == expected_rc
        assert updated_idx.orientation == C.BarcodeOrientation.FORWARD

    def test_verify_dual_index_both_orientations(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Dual-index library with both i7 and i5 unvalidated gets corrected."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        idx = _add_index(
            session, lib,
            sequence_i7="ACGTACGT",
            sequence_i5="TGCAACGT",
            orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED,
        )
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)
        response = self._complete_workflow(
            client, insider_token, params, verify_page, ["forward"]
        )
        assert response.status_code in (200, 204)

        session.expire_all()
        updated_idx = session.get_one(Q.library_index.select(id=idx.id))
        assert updated_idx.orientation == C.BarcodeOrientation.FORWARD

    def test_verify_null_orientation_custom_index(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """A custom index without orientation is picked up and can be reverse-complemented."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        original_seq = "ACGTACGT"
        idx = _add_index(session, lib, sequence_i7=original_seq, orientation=None)
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)
        assert verify_page.status_code == 200
        assert _verify_rows(verify_page) == [[f"{lib.name} [{idx.id}]", "Forward", "i7_index", original_seq, "", ""]]

        response = self._complete_workflow(
            client, insider_token, params, verify_page, ["reverse_complement"]
        )
        assert response.status_code in (200, 204)

        session.expire_all()
        updated_idx = session.get_one(Q.library_index.select(id=idx.id))
        assert updated_idx.sequence_i7 == models.Barcode.reverse_complement(original_seq)
        assert updated_idx.orientation == C.BarcodeOrientation.FORWARD
        sr = session.get_one(Q.seq_request.select(id=sr.id))
        assert sr.get_review_checklist()["check_barcodes"] is True

    def test_verify_kit_i7_custom_i5(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Kit i7 with a custom i5 needs manual verification; RC only changes the custom i5."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        kit = create_index_kit(session)
        seq_i7, seq_i5 = "ACGTACGT", "TTGGCCAA"
        idx = _add_index(
            session, lib,
            sequence_i7=seq_i7, sequence_i5=seq_i5,
            index_kit_i7=kit, name_i7="i7_index",
            orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED,
        )
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)
        assert verify_page.status_code == 200

        response = self._complete_workflow(
            client, insider_token, params, verify_page, ["reverse_complement"]
        )
        assert response.status_code in (200, 204)

        session.expire_all()
        updated_idx = session.get_one(Q.library_index.select(id=idx.id))
        assert updated_idx.sequence_i7 == seq_i7
        assert updated_idx.sequence_i5 == models.Barcode.reverse_complement(seq_i5)
        assert updated_idx.orientation == C.BarcodeOrientation.FORWARD

    def test_verify_kit_index_reverse_complement_rejected(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Reverse complement cannot be chosen for an index from a kit."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        kit = create_index_kit(session)
        idx = _add_index(session, lib, index_kit_i7=kit, name_i7="i7_index")
        session.commit()

        params = {"seq_request_id": sr.id, "uuid": str(uuid_mod.uuid4())}
        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)
        response = post_form(
            client, f"{PREFIX}/verify-orientations",
            _verify_payload(verify_page, ["reverse_complement"]),
            token=insider_token, params=params,
        )
        assert_form_invalid(response, "Barcodes from a kit are always in forward orientation.")

        session.expire_all()
        assert session.get_one(Q.library_index.select(id=idx.id)).orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED

    def test_verify_sorted_rows_match_their_index(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Rows are matched to their index by content, so sorting the spreadsheet is safe."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        idx_a = _add_index(session, lib, sequence_i7="AAAACCCC")
        idx_b = _add_index(session, lib, sequence_i7="GGGGTTTT")
        session.commit()

        params = {"seq_request_id": sr.id, "uuid": str(uuid_mod.uuid4())}
        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)
        rows = _verify_rows(verify_page)
        assert [row[3] for row in rows] == ["AAAACCCC", "GGGGTTTT"]

        # Submit in reverse order: reverse complement only idx_b
        rows = rows[::-1]
        rows[0][1], rows[1][1] = "Reverse Complement", "Forward"
        post_form(
            client, f"{PREFIX}/verify-orientations",
            spreadsheet_payload(VERIFY_COLUMNS, rows),
            token=insider_token, params=params,
        )
        post_form(client, f"{PREFIX}/complete-index-check", {}, token=insider_token, params=params)

        session.expire_all()
        assert session.get_one(Q.library_index.select(id=idx_a.id)).sequence_i7 == "AAAACCCC"
        assert session.get_one(Q.library_index.select(id=idx_b.id)).sequence_i7 == models.Barcode.reverse_complement("GGGGTTTT")

    def test_verify_read_only_edits_are_ignored(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Only the index id and orientation are read: a changed sequence is not saved."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        idx = _add_index(session, lib, sequence_i7="ACGTACGT")
        session.commit()

        params = {"seq_request_id": sr.id, "uuid": str(uuid_mod.uuid4())}
        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)
        rows = _verify_rows(verify_page)
        rows[0][3] = "TTTTTTTT"
        response = post_form(
            client, f"{PREFIX}/verify-orientations",
            spreadsheet_payload(VERIFY_COLUMNS, rows),
            token=insider_token, params=params,
        )
        assert response.status_code == 200
        post_form(client, f"{PREFIX}/complete-index-check", {}, token=insider_token, params=params)

        session.expire_all()
        updated_idx = session.get_one(Q.library_index.select(id=idx.id))
        assert updated_idx.sequence_i7 == "ACGTACGT"
        assert updated_idx.orientation == C.BarcodeOrientation.FORWARD

    def test_verify_unknown_index_id_rejected(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """A row whose index id is not part of the workflow is rejected and nothing is saved."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        idx = _add_index(session, lib, sequence_i7="ACGTACGT")
        session.commit()

        params = {"seq_request_id": sr.id, "uuid": str(uuid_mod.uuid4())}
        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)
        rows = _verify_rows(verify_page)
        rows[0][0] = f"{lib.name} [{idx.id + 100000}]"
        response = post_form(
            client, f"{PREFIX}/verify-orientations",
            spreadsheet_payload(VERIFY_COLUMNS, rows),
            token=insider_token, params=params,
        )
        assert_form_invalid(response, "Row does not match an index of the selected libraries.")

        session.expire_all()
        assert session.get_one(Q.library_index.select(id=idx.id)).orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED

    def test_complete_summary_shows_saved_index(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """The confirmation step shows the orientation that gets assigned and the barcode as it will be saved."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        idx = _add_index(session, lib, sequence_i7="AAAACCCC")
        session.commit()

        params = {"seq_request_id": sr.id, "uuid": str(uuid_mod.uuid4())}
        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)
        response = post_form(
            client, f"{PREFIX}/verify-orientations",
            _verify_payload(verify_page, ["reverse_complement"]),
            token=insider_token, params=params,
        )
        assert response.status_code == 200
        assert C.BarcodeOrientation.FORWARD.display_name in response.text
        assert "index-badge" in response.text
        assert models.Barcode.reverse_complement("AAAACCCC") in response.text

        # The preview must not have been saved; the index only changes on Complete
        session.expire_all()
        unchanged = session.get_one(Q.library_index.select(id=idx.id))
        assert unchanged.sequence_i7 == "AAAACCCC"
        assert unchanged.orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED
        assert len(session.get_one(Q.library.select(id=lib.id)).indices) == 1

    def test_verify_prefills_and_restores_orientation(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """REVERSE_COMPLEMENT_NOT_VALIDATED is pre-filled as Reverse Complement, and choices survive going back."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, sequence_i7="AAAACCCC", orientation=C.BarcodeOrientation.REVERSE_COMPLEMENT_NOT_VALIDATED)
        _add_index(session, lib, sequence_i7="GGGGTTTT", orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED)
        session.commit()

        params = {"seq_request_id": sr.id, "uuid": str(uuid_mod.uuid4())}
        verify_page = self._navigate_to_verify(client, insider_token, params, [lib.id], session)
        assert [row[1] for row in _verify_rows(verify_page)] == ["Reverse Complement", "Forward"]

        post_form(
            client, f"{PREFIX}/verify-orientations",
            _verify_payload(verify_page, ["forward", "reverse_complement"]),
            token=insider_token, params=params,
        )
        verify_page = get(client, f"{PREFIX}/verify-orientations", insider_token, params=params, htmx=True)
        assert verify_page.status_code == 200
        assert [row[1] for row in _verify_rows(verify_page)] == ["Forward", "Reverse Complement"]


# ── Phase D: Completion ──────────────────────────────────────────────────────

class TestComplete:
    def _navigate_and_complete(
        self, client, insider_token, params, library_ids, orientations,
    ):
        """Helper to run full workflow and return final response."""
        get(client, f"{PREFIX}/begin", insider_token, params=params, htmx=True)
        verify_page = post_form(
            client, f"{PREFIX}/select-libraries",
            {"selected_library_ids": json.dumps(library_ids)},
            token=insider_token, params=params,
        )
        post_form(
            client, f"{PREFIX}/verify-orientations",
            _verify_payload(verify_page, orientations),
            token=insider_token, params=params,
        )
        return post_form(
            client, f"{PREFIX}/complete-index-check",
            {},
            token=insider_token, params=params,
        )

    def test_complete_persists_orientation(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """After completion, LibraryIndex.orientation == FORWARD."""
        sr = create_seq_request(session, insider)
        lib1 = create_library(session, insider, sr)
        lib2 = create_library(session, insider, sr)
        idx1 = _add_index(session, lib1, sequence_i7="AAAAAA")
        idx2 = _add_index(session, lib2, sequence_i7="CCCCCC")
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        self._navigate_and_complete(
            client, insider_token, params, [lib1.id, lib2.id],
            ["forward", "forward"],
        )

        session.expire_all()
        assert session.get_one(Q.library_index.select(id=idx1.id)).orientation == C.BarcodeOrientation.FORWARD
        assert session.get_one(Q.library_index.select(id=idx2.id)).orientation == C.BarcodeOrientation.FORWARD

    def test_complete_redis_cleanup(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """After completion, Redis keys for the workflow UUID are deleted."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, sequence_i7="ACGTACGT")
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        self._navigate_and_complete(
            client, insider_token, params, [lib.id],
            ["forward"],
        )

        from redis import Redis
        r = Redis(connection_pool=client.app.state.redis_pool)
        keys = r.keys(f"IndexCheckWorkflow:{workflow_uuid}:*")
        assert len(keys) == 0

    def test_complete_redirects_to_seq_request(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """After completion, redirect goes back to the seq_request page."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, sequence_i7="ACGTACGT")
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        response = self._navigate_and_complete(
            client, insider_token, params, [lib.id],
            ["forward"],
        )
        assert_htmx_redirect(response, f"/seq_requests/{sr.id}")

    def test_complete_marks_review_checklist(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Completing the workflow from a seq_request marks the index_check review step."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, sequence_i7="ACGTACGT")
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        self._navigate_and_complete(
            client, insider_token, params, [lib.id],
            ["forward"],
        )

        session.expire_all()
        sr = session.get_one(Q.seq_request.select(id=sr.id))
        checklist = sr.get_review_checklist()
        assert checklist["index_check"] is True
        assert checklist["check_barcodes"] is True

    def test_complete_partial_does_not_mark_review_checklist(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """If unvalidated indices remain in the request, the index_check step stays unchecked."""
        sr = create_seq_request(session, insider)
        lib1 = create_library(session, insider, sr)
        lib2 = create_library(session, insider, sr)
        _add_index(session, lib1, sequence_i7="ACGTACGT")
        _add_index(session, lib2, sequence_i7="TTTTAAAA")
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        self._navigate_and_complete(
            client, insider_token, params, [lib1.id],
            ["forward"],
        )

        session.expire_all()
        sr = session.get_one(Q.seq_request.select(id=sr.id))
        assert sr.get_review_checklist()["index_check"] is False


# ── Phase E: Review checklist integration ────────────────────────────────────

class TestReviewChecklist:
    def test_index_check_checklist_default_pooled(
        self,
        session: SyncSession,
        insider: models.User,
    ):
        """For POOLED_LIBRARIES submission, index_check defaults to False."""
        sr = create_seq_request(session, insider, submission_type=C.SubmissionType.POOLED_LIBRARIES)
        session.commit()
        checklist = sr.get_review_checklist()
        assert checklist["index_check"] is False

    def test_index_check_checklist_default_unpooled(
        self,
        session: SyncSession,
        insider: models.User,
    ):
        """For UNPOOLED_LIBRARIES submission, index_check defaults to False."""
        sr = create_seq_request(session, insider, submission_type=C.SubmissionType.UNPOOLED_LIBRARIES)
        session.commit()
        checklist = sr.get_review_checklist()
        assert checklist["index_check"] is False

    def test_index_check_checklist_default_raw_samples(
        self,
        session: SyncSession,
        insider: models.User,
    ):
        """For RAW_SAMPLES submission, index_check defaults to None (not-applicable)."""
        sr = create_seq_request(session, insider, submission_type=C.SubmissionType.RAW_SAMPLES)
        session.commit()
        checklist = sr.get_review_checklist()
        assert checklist["index_check"] is None

    def test_index_check_checklist_default_qc_only(
        self,
        session: SyncSession,
        insider: models.User,
    ):
        """For QC_ONLY submission, index_check defaults to None (not-applicable)."""
        sr = create_seq_request(session, insider, submission_type=C.SubmissionType.QC_ONLY)
        session.commit()
        checklist = sr.get_review_checklist()
        assert checklist["index_check"] is None

    def test_index_check_manual_check_rejected(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """index_check cannot be checked via the generic review-check endpoint."""
        sr = create_seq_request(session, insider)
        session.commit()

        response = post_form(
            client, f"/htmx/seq_requests/{sr.id}/review-check/index_check",
            {}, token=insider_token, htmx=True,
        )
        assert response.status_code == 400

        session.expire_all()
        sr = session.get_one(Q.seq_request.select(id=sr.id))
        assert sr.get_review_checklist()["index_check"] is False

    def test_check_barcodes_unvalidated_custom_index(
        self,
        session: SyncSession,
        insider: models.User,
    ):
        """A custom index that is not FORWARD leaves check_barcodes incomplete."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, orientation=C.BarcodeOrientation.FORWARD)
        _add_index(session, lib, orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED)
        session.commit()
        assert sr.get_review_checklist()["check_barcodes"] is False

    def test_check_barcodes_all_forward(
        self,
        session: SyncSession,
        insider: models.User,
    ):
        """All indices FORWARD completes check_barcodes."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, orientation=C.BarcodeOrientation.FORWARD)
        session.commit()
        assert sr.get_review_checklist()["check_barcodes"] is True

    def test_check_barcodes_kit_index(
        self,
        session: SyncSession,
        insider: models.User,
    ):
        """A kit index counts as checked regardless of orientation."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        kit = create_index_kit(session)
        _add_index(session, lib, orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED, index_kit_i7=kit)
        session.commit()
        assert sr.get_review_checklist()["check_barcodes"] is True

    def test_check_barcodes_ignores_stored_flag(
        self,
        session: SyncSession,
        insider: models.User,
    ):
        """A stored check_barcodes flag does not override the index state."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, orientation=C.BarcodeOrientation.REVERSE_COMPLEMENT_NOT_VALIDATED)
        sr.review_checklist = {"check_barcodes": True}
        session.save(sr)
        session.commit()
        assert sr.get_review_checklist()["check_barcodes"] is False

    def test_check_barcodes_not_applicable_raw_samples(
        self,
        session: SyncSession,
        insider: models.User,
    ):
        """For RAW_SAMPLES submissions check_barcodes is complete regardless of indices."""
        sr = create_seq_request(session, insider, submission_type=C.SubmissionType.RAW_SAMPLES)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED)
        session.commit()
        assert sr.get_review_checklist()["check_barcodes"] is True

    def test_check_barcodes_manual_check_uncheck_rejected(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """check_barcodes cannot be checked or unchecked manually."""
        sr = create_seq_request(session, insider)
        session.commit()

        for action in ("review-check", "review-uncheck"):
            response = post_form(
                client, f"/htmx/seq_requests/{sr.id}/{action}/check_barcodes",
                {}, token=insider_token, htmx=True,
            )
            assert response.status_code == 400

        session.expire_all()
        sr = session.get_one(Q.seq_request.select(id=sr.id))
        assert "check_barcodes" not in (sr.review_checklist or {})

    def test_review_checklist_renders(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """The review checklist renders without manual check buttons for derived steps."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED)
        session.commit()

        response = get(client, f"/htmx/seq_requests/{sr.id}/review-checklist", insider_token, htmx=True)
        assert response.status_code == 200
        assert "step=check_barcodes" not in response.text
        assert "review-check/check_barcodes" not in response.text
        assert "review-check/index_check" not in response.text


# ── Phase F: Edge cases ──────────────────────────────────────────────────────

class TestEdgeCases:
    def _run_full_workflow(
        self, client, insider_token, sr_id, library_ids, orientations,
    ):
        """Run the full workflow and return the final response."""
        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr_id, "uuid": workflow_uuid}

        get(client, f"{PREFIX}/begin", insider_token, params=params, htmx=True)
        verify_page = post_form(
            client, f"{PREFIX}/select-libraries",
            {"selected_library_ids": json.dumps(library_ids)},
            token=insider_token, params=params,
        )
        post_form(
            client, f"{PREFIX}/verify-orientations",
            _verify_payload(verify_page, orientations),
            token=insider_token, params=params,
        )
        return post_form(
            client, f"{PREFIX}/complete-index-check",
            {},
            token=insider_token, params=params,
        )

    def test_index_check_reverse_complement_not_validated(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Library with REVERSE_COMPLEMENT_NOT_VALIDATED orientation is included and RC'd."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        original_seq = "ACGTACGT"
        idx = _add_index(
            session, lib,
            sequence_i7=original_seq,
            orientation=C.BarcodeOrientation.REVERSE_COMPLEMENT_NOT_VALIDATED,
        )
        session.commit()

        response = self._run_full_workflow(
            client, insider_token, sr.id, [lib.id],
            ["reverse_complement"],
        )
        assert_htmx_redirect(response, f"/seq_requests/{sr.id}")

        session.expire_all()
        updated_idx = session.get_one(Q.library_index.select(id=idx.id))
        expected_rc = models.Barcode.reverse_complement(original_seq)
        assert updated_idx.sequence_i7 == expected_rc

    def test_index_check_mixed_validated_and_not(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Library with mixed orientations processes only unvalidated indices."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        # One validated index
        idx_validated = _add_index(
            session, lib,
            sequence_i7="AAAAAA",
            orientation=C.BarcodeOrientation.FORWARD,
        )
        # One unvalidated index
        idx_unvalidated = _add_index(
            session, lib,
            sequence_i7="CCCCCC",
            orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED,
        )
        session.commit()

        response = self._run_full_workflow(
            client, insider_token, sr.id, [lib.id],
            ["forward"],
        )
        assert_htmx_redirect(response, f"/seq_requests/{sr.id}")

        session.expire_all()
        # Validated index should still be FORWARD
        assert session.get_one(Q.library_index.select(id=idx_validated.id)).orientation == C.BarcodeOrientation.FORWARD

    def test_index_check_lab_prep_context(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Workflow started with lab_prep_id works."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, sequence_i7="ACGTACGT")
        session.commit()

        # Create a lab prep (simplified — use any valid lab_prep_id approach)
        lp = session.save(Q.lab_prep.create(
            name="Test Lab Prep",
            creator=insider,
            number=1,
            checklist_type=C.LabChecklistType.RNA_SEQ,
            service_type=C.ServiceType.BULK_RNA_SEQ,
        ), flush=True)
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"lab_prep_id": lp.id, "uuid": workflow_uuid}

        response = get(
            client, f"{PREFIX}/begin", insider_token,
            params=params, htmx=True,
        )
        assert response.status_code == 200

    def test_index_check_pool_context(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Workflow started with pool_id works."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, sequence_i7="ACGTACGT")
        pool = session.save(Q.pool.create(
            name="Test Pool",
            owner_id=insider.id,
            contact_name="Test",
            contact_email="test@example.com",
            seq_request_id=sr.id,
            pool_type=C.PoolType.EXTERNAL,
            clone_number=0,
        ), flush=True)
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"pool_id": pool.id, "uuid": workflow_uuid}

        response = get(
            client, f"{PREFIX}/begin", insider_token,
            params=params, htmx=True,
        )
        assert response.status_code == 200

    def test_index_check_previous_navigation(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Back button returns to previous step with preserved state."""
        sr = create_seq_request(session, insider)
        lib = create_library(session, insider, sr)
        _add_index(session, lib, sequence_i7="ACGTACGT")
        session.commit()

        workflow_uuid = str(uuid_mod.uuid4())
        params = {"seq_request_id": sr.id, "uuid": workflow_uuid}

        # Go to step 1
        get(client, f"{PREFIX}/begin", insider_token, params=params, htmx=True)
        # Go to step 2
        post_form(
            client, f"{PREFIX}/select-libraries",
            {"selected_library_ids": json.dumps([lib.id])},
            token=insider_token, params=params,
        )

        # Now go back to step 1
        response = get(
            client, f"{PREFIX}/select-libraries",
            insider_token,
            params={**params, "step": "SelectLibrariesForm"},
        )
        assert response.status_code == 200

# ── Barcode colors in the clash check ────────────────────────────────────────

class TestBarcodeClashColors:
    def test_check_clashes_uses_index_badge_colors(
        self,
        client: OpenGSyncTestClient,
        session: SyncSession,
        insider: models.User,
        insider_token: str,
    ):
        """Check Clashes colors barcodes like library_index_cell: validated custom barcodes are not red."""
        sr = create_seq_request(session, insider)
        kit = create_index_kit(session)
        pool = session.save(Q.pool.create(
            name="Clash Pool", owner_id=insider.id, contact_name="Test", contact_email="test@example.com",
            seq_request_id=sr.id, pool_type=C.PoolType.EXTERNAL, clone_number=0,
        ), flush=True)
        barcodes = {
            "AAAACCCC": (C.BarcodeOrientation.FORWARD, None, "badge-primary"),
            "CCCCGGGG": (C.BarcodeOrientation.FORWARD_NOT_VALIDATED, None, "badge-warning"),
            "GGGGTTTT": (None, None, "badge-danger"),
            "TTTTAAAA": (C.BarcodeOrientation.FORWARD, kit, "badge-success"),
        }
        for sequence, (orientation, index_kit, _) in barcodes.items():
            lib = create_library(session, insider, sr)
            lib.pool_id = pool.id
            _add_index(
                session, lib, sequence_i7=sequence, orientation=orientation,
                index_kit_i7=index_kit, name_i7="A1" if index_kit else None,
            )
        session.commit()

        response = get(
            client, client.app.url_path_for("CheckBarcodeClashesAction.Render"), insider_token,
            params={"pool_id": pool.id}, htmx=True,
        )
        assert response.status_code == 200
        for sequence, (_, _, expected) in barcodes.items():
            classes = re.findall(rf'class="badge index-badge index-badges-[^" ]+ ([a-z-]+)"[^>]*>{sequence}<', response.text)
            assert classes and set(classes) == {expected}, (sequence, classes)
