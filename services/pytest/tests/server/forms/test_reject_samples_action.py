"""RejectSamplesAction: mark samples of a lab prep's multiplexed libraries as failed.

The spreadsheet lists every sample of the lab prep's multiplexed libraries, with ``x`` in
the Reject column for samples that are already REJECTED. On submit, marked samples get
status REJECTED and unmarked REJECTED samples go back to STORED. Samples stay linked to
their library and library statuses are not changed.

The sample is one read-only ``DBObjectColumn`` ("name [id]") whose options are the prep's
samples; every sample must be listed exactly once, so samples outside the prep or omitted
rows fail validation.

Access is insider-only.
"""

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, categories as C, models

from ...db.create_units import create_project, create_sample
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
    spreadsheet_payload,
)
from .test_sample_pooling_action import Prep

PREFIX = "/htmx/actions/reject-samples"
COLUMNS = ["Sample", "Pool", "Status", "Reject"]


def _path(lab_prep_id: int) -> str:
    return f"{PREFIX}/{lab_prep_id}"


def _cell(sample: models.Sample) -> str:
    return f"{sample.name} [{sample.id}]"


def _rows(prep: Prep, rejected: set[models.Sample]) -> list[list[str]]:
    return [[_cell(sample), pool, "", "x" if sample in rejected else ""] for sample, pool in prep.pools().items()]


def _payload(prep: Prep, rejected: set[models.Sample]) -> dict[str, str]:
    return spreadsheet_payload(COLUMNS, _rows(prep, rejected))


def _statuses(session: SyncSession, prep: Prep) -> dict[str, C.SampleStatus | None]:
    session.expire_all()
    return {sample.name: sample.status for sample in prep.samples}


@pytest.fixture
def prep(session: SyncSession, user, insider) -> Prep:
    prep = Prep(session, user, insider)
    for sample in prep.samples:
        sample.status = C.SampleStatus.STORED
    session.commit()
    return prep


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_lists_samples_and_prefills_rejected(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    prep.s2.status = C.SampleStatus.REJECTED
    session.commit()

    response = get(client, _path(prep.lab_prep.id), insider_token)

    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text
    for text in (*(_cell(sample) for sample in prep.samples), "PoolA", "PoolB", C.SampleStatus.REJECTED.display_name):
        assert text in response.text
    assert "Sample ID" not in response.text


def test_render_omits_non_multiplexed_libraries(
    client: TestClient, session: SyncSession, prep: Prep, user, insider_token: str,
):
    sample = create_sample(session, user, create_project(session, user))
    sample.name = "PlainSample"
    prep.library("PlainPool", C.LibraryType.BULK_RNA_SEQ, [sample], mux_type=None)
    session.commit()

    response = get(client, _path(prep.lab_prep.id), insider_token)

    assert response.status_code == 200
    assert "PlainSample" not in response.text


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_is_denied(client: TestClient, session: SyncSession, prep: Prep, user_token: str):
    assert get(client, _path(prep.lab_prep.id), user_token).status_code == 403
    assert post_form(client, _path(prep.lab_prep.id), _payload(prep, {prep.s2}), token=user_token).status_code == 403
    assert _statuses(session, prep)["S2"] == C.SampleStatus.STORED


def test_unknown_lab_prep_is_404(client: TestClient, insider_token: str):
    assert get(client, _path(999999), insider_token).status_code == 404


def test_csrf_mismatch_changes_nothing(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    response = post_form_csrf_mismatch(client, _path(prep.lab_prep.id), _payload(prep, {prep.s2}), token=insider_token)

    assert response.status_code != 204
    assert _statuses(session, prep)["S2"] == C.SampleStatus.STORED


# ── Submit ──────────────────────────────────────────────────────────────────


def test_reject_keeps_sample_in_its_library(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    layout = prep.layout()

    response = post_form(client, _path(prep.lab_prep.id), _payload(prep, {prep.s2}), token=insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert_flash(response, "Rejected 1 and restored 0 sample(s).", category="success")
    assert _statuses(session, prep) == {
        "S1": C.SampleStatus.STORED, "S2": C.SampleStatus.REJECTED,
        "S3": C.SampleStatus.STORED, "S4": C.SampleStatus.STORED,
    }
    assert prep.layout() == layout
    assert {lib.id for lib in prep.libraries().values()} == {prep.pool_a.id, prep.pool_b.id}
    assert all(lib.status == C.LibraryStatus.ACCEPTED for lib in prep.libraries().values())


def test_rejecting_all_samples_of_a_library_keeps_library_status(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    response = post_form(client, _path(prep.lab_prep.id), _payload(prep, {prep.s1, prep.s2}), token=insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.libraries()["PoolA_10XFLEXGEX"].status == C.LibraryStatus.ACCEPTED


def test_clearing_x_restores_stored(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    prep.s2.status = C.SampleStatus.REJECTED
    prep.s3.status = C.SampleStatus.REJECTED
    session.commit()

    response = post_form(client, _path(prep.lab_prep.id), _payload(prep, {prep.s3}), token=insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert_flash(response, "Rejected 0 and restored 1 sample(s).", category="success")
    statuses = _statuses(session, prep)
    assert statuses["S2"] == C.SampleStatus.STORED
    assert statuses["S3"] == C.SampleStatus.REJECTED


def test_samples_outside_the_prep_are_untouched(
    client: TestClient, session: SyncSession, prep: Prep, user, insider_token: str,
):
    outsider = create_sample(session, user, create_project(session, user))
    outsider.status = C.SampleStatus.STORED
    session.commit()
    payload = spreadsheet_payload(COLUMNS, [*_rows(prep, set()), [_cell(outsider), "PoolA", "", "x"]])

    response = post_form(client, _path(prep.lab_prep.id), payload, token=insider_token)

    assert_form_invalid(response, f"Invalid value '{_cell(outsider)}'")
    session.expire_all()
    assert outsider.status == C.SampleStatus.STORED


def test_omitted_sample_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    """Leaving out a REJECTED sample's row must not restore it: every sample of the prep is required."""
    prep.s2.status = C.SampleStatus.REJECTED
    session.commit()
    rows = [row for row in _rows(prep, set()) if row[0] != _cell(prep.s2)]

    response = post_form(client, _path(prep.lab_prep.id), spreadsheet_payload(COLUMNS, rows), token=insider_token)

    assert_form_invalid(response, f"missing option '{_cell(prep.s2)}'")
    assert _statuses(session, prep)["S2"] == C.SampleStatus.REJECTED


def test_duplicate_sample_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    rows = _rows(prep, set())
    rows.append([_cell(prep.s2), "PoolA", "", "x"])

    response = post_form(client, _path(prep.lab_prep.id), spreadsheet_payload(COLUMNS, rows), token=insider_token)

    assert_form_invalid(response, "is not unique")
    assert _statuses(session, prep)["S2"] == C.SampleStatus.STORED


def test_prep_table_template_skips_rejected_samples(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    import io
    import openpyxl

    prep.s2.status = C.SampleStatus.REJECTED
    session.commit()

    response = get(
        client, f"/htmx/lab_preps/{prep.lab_prep.id}/prep-spreadsheet-template", insider_token,
        params={"checklist_id": C.LabChecklistType.TENX.id},
    )

    assert response.status_code == 200
    sheet = openpyxl.load_workbook(io.BytesIO(response.content))["FLEX_table"]
    names = {cell.value for row in sheet.iter_rows(min_row=2) for cell in row if isinstance(cell.value, str)}
    assert {"S1", "S3", "S4"} <= names
    assert "S2" not in names
