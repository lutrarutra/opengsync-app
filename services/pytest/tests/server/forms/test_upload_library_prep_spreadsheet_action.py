"""UploadLibraryPrepSpreadsheetAction: upload the lab prep table (``prep_table`` sheet).

As legacy ``lab_preps_htmx.prep_table_upload_form`` / ``LibraryPrepForm``: insider-only.
Rows without ``library_id`` and ``library_name`` are ignored and rows with pool ``t`` are
not validated. Each row's library must be part of the prep and its name must match;
plate wells must be unique per plate. On success the file is stored as the prep's
``LIBRARY_PREP_FILE`` (replacing an earlier one), the prep's plates are replaced (one per
``plate`` value, ``P-<prep>`` / ``P-<prep>-<plate>``), pool ``x`` marks the library FAILED
and ``lib_conc_ng_ul`` sets its qubit concentration.

FastAPI also places each library in its plate well (legacy computed the well index but
the link was commented out).
"""

import io
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import config

from ...db.create_units import create_lab_prep, create_library, create_seq_request
from .._http import CSRF, assert_flash, cookie_header, assert_form_invalid, assert_htmx_redirect, get

PREFIX = "/htmx/lab_preps/upload-prep-table"
COLUMNS = [
    "library_id", "library_name", "requestor", "pool", "plate", "plate_well", "index_well",
    "kit_i7", "name_i7", "sequence_i7", "kit_i5", "name_i5", "sequence_i5", "lib_conc_ng_ul",
]


def _path(lab_prep_id: int) -> str:
    return f"{PREFIX}/{lab_prep_id}"


def _xlsx(rows: list[dict[str, Any]], sheet_name: str = "prep_table", columns: list[str] = COLUMNS) -> bytes:
    buffer = io.BytesIO()
    pd.DataFrame(rows, columns=columns).to_excel(buffer, sheet_name=sheet_name, index=False)
    return buffer.getvalue()


def _csv(rows: list[dict[str, Any]]) -> bytes:
    return pd.DataFrame(rows, columns=COLUMNS).to_csv(index=False).encode()


def _upload(
    client: TestClient, lab_prep_id: int, content: bytes | None, token: str | None,
    filename: str = "prep.xlsx", csrf: str = CSRF,
):
    """POST the file as the template does (multipart, field ``spreadsheet``)."""
    client.cookies.set("csrf_token", CSRF)
    files = {"spreadsheet": (filename, content, "application/octet-stream")} if content is not None else None
    return client.post(
        _path(lab_prep_id), data={"csrf_token": csrf}, files=files,
        headers=cookie_header(client, token), follow_redirects=False,
    )


def _row(library: models.Library, **values: Any) -> dict[str, Any]:
    return {"library_id": library.id, "library_name": library.name, **values}


def _reload(session: SyncSession, lab_prep: models.LabPrep) -> models.LabPrep:
    session.expire_all()
    return session.get_one(Q.lab_prep.select(id=lab_prep.id))


def _plates(session: SyncSession, lab_prep: models.LabPrep) -> dict[str, dict[int, int]]:
    """Plate name → {well_idx: library_id}."""
    lab_prep = _reload(session, lab_prep)
    return {
        plate.name: {link.well_idx: link.library_id for link in plate.sample_links}
        for plate in lab_prep.plates
    }


@pytest.fixture
def media_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config.settings.app_config, "media_folder", str(tmp_path))
    return tmp_path


class Prep:
    def __init__(self, session: SyncSession, insider: models.User, user: models.User):
        self.lab_prep = create_lab_prep(session, insider)
        seq_request = create_seq_request(session, user)
        self.libraries: list[models.Library] = []
        for _ in range(3):
            library = create_library(session, user, seq_request)
            library.lab_prep_id = self.lab_prep.id
            session.save(library, flush=True)
            self.libraries.append(library)
        session.commit()

    @property
    def id(self) -> int:
        return self.lab_prep.id

    @property
    def name(self) -> str:
        return self.lab_prep.name


@pytest.fixture
def prep(session: SyncSession, insider, user, media_folder: Path) -> Prep:
    return Prep(session, insider, user)


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render(client: TestClient, prep: Prep, insider_token: str):
    response = get(client, _path(prep.id), insider_token)

    assert response.status_code == 200, response.text
    assert "Upload Library Preparation Table" in response.text
    assert 'type="file"' in response.text
    assert prep.name in response.text


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_is_denied(client: TestClient, prep: Prep, user_token: str):
    assert get(client, _path(prep.id), user_token).status_code == 403
    response = _upload(client, prep.id, _xlsx([_row(prep.libraries[0], plate_well="A1")]), user_token)
    assert response.status_code == 403


def test_client_with_invalid_submission_is_still_denied(client: TestClient, prep: Prep, user_token: str):
    """The role check must not come after validation (which would render the form back)."""
    assert _upload(client, prep.id, b"not a spreadsheet", user_token).status_code == 403


def test_anonymous_is_redirected_to_login(client: TestClient, prep: Prep):
    for response in (get(client, _path(prep.id)), _upload(client, prep.id, _xlsx([]), None)):
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")


def test_unknown_lab_prep_is_404(client: TestClient, insider_token: str):
    assert get(client, _path(999999), insider_token).status_code == 404


def test_csrf_mismatch_changes_nothing(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str, media_folder: Path,
):
    response = _upload(client, prep.id, _xlsx([_row(prep.libraries[0], plate_well="A1")]), insider_token, csrf="other")

    assert response.status_code != 204
    assert _reload(session, prep.lab_prep).prep_file is None
    assert _plates(session, prep.lab_prep) == {}


# ── Submit: persistence ─────────────────────────────────────────────────────


def test_upload_stores_prep_file(
    client: TestClient, session: SyncSession, prep: Prep, insider, insider_token: str, media_folder: Path,
):
    content = _xlsx([_row(lib, plate_well=f"A{i + 1}") for i, lib in enumerate(prep.libraries)])

    response = _upload(client, prep.id, content, insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.id}")
    assert_flash(response, "Table saved!", category="success")

    prep_file = _reload(session, prep.lab_prep).prep_file
    assert prep_file is not None
    assert prep_file.type == C.MediaFileType.LIBRARY_PREP_FILE
    assert prep_file.uploader_id == insider.id
    assert prep_file.size_bytes == len(content)
    assert (media_folder / prep_file.path).read_bytes() == content



def test_failure_while_saving_leaves_no_file_or_records(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str, media_folder: Path, monkeypatch: pytest.MonkeyPatch,
):
    """The file is written only after the database changes succeeded (§5: no partial records or files)."""
    def fail(self, well: str) -> int:
        raise RuntimeError("unexpected")
    monkeypatch.setattr(models.Plate, "get_well_idx", fail)
    lenient = TestClient(client.app, raise_server_exceptions=False)
    lenient.cookies = client.cookies

    response = _upload(lenient, prep.id, _xlsx([_row(prep.libraries[0], plate_well="A1")]), insider_token)

    assert response.status_code == 500
    assert [path for path in media_folder.rglob("*") if path.is_file()] == []
    lab_prep = _reload(session, prep.lab_prep)
    assert lab_prep.prep_file is None and lab_prep.plates == []

def test_stored_file_is_readable_as_prep_table(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str, media_folder: Path,
):
    """The reindex and pooling workflows read the stored file's ``prep_table`` sheet."""
    _upload(client, prep.id, _xlsx([_row(prep.libraries[0], plate_well="A1", pool="1")]), insider_token)

    prep_file = _reload(session, prep.lab_prep).prep_file
    assert prep_file is not None
    df = pd.read_excel(media_folder / prep_file.path, sheet_name="prep_table")
    assert df["library_id"].tolist() == [prep.libraries[0].id]


def test_reupload_replaces_prep_file(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str, media_folder: Path,
):
    _upload(client, prep.id, _xlsx([_row(prep.libraries[0], plate_well="A1")]), insider_token)
    first = _reload(session, prep.lab_prep).prep_file
    assert first is not None
    first_id, first_uuid = first.id, first.uuid

    content = _xlsx([_row(prep.libraries[1], plate_well="B1")])
    response = _upload(client, prep.id, content, insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.id}")
    files = [f for f in _reload(session, prep.lab_prep).media_files if f.type == C.MediaFileType.LIBRARY_PREP_FILE]
    assert [f.id for f in files] == [first_id]
    assert files[0].uuid != first_uuid
    assert (media_folder / files[0].path).read_bytes() == content


@pytest.mark.parametrize("filename", ["prep.csv", "prep.tsv"])
def test_non_xlsx_upload_is_rejected(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str, filename: str,
):
    """Only .xlsx: every reader of the stored prep file reads its ``prep_table`` sheet."""
    content = _csv([_row(prep.libraries[0], plate_well="A1")])

    response = _upload(client, prep.id, content, insider_token, filename=filename)

    assert_form_invalid(response, "Allowed types: xlsx.")
    _assert_unchanged(session, prep)


def test_libraries_are_placed_on_default_plate(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    a, b, c = prep.libraries
    content = _xlsx([_row(a, plate_well="A1"), _row(b, plate_well="b2"), _row(c, plate_well=" H12 ")])

    _upload(client, prep.id, content, insider_token)

    # Wells are cleaned (strip + upper); index = row * 12 + col.
    assert _plates(session, prep.lab_prep) == {f"P-{prep.name}": {0: a.id, 13: b.id, 95: c.id}}


def test_zero_padded_wells_are_accepted(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    a = prep.libraries[0]
    _upload(client, prep.id, _xlsx([_row(a, plate_well="A01")]), insider_token)

    assert _plates(session, prep.lab_prep) == {f"P-{prep.name}": {0: a.id}}


def test_plate_column_creates_one_plate_per_value(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    a, b, c = prep.libraries
    content = _xlsx([
        _row(a, plate="X", plate_well="A1"), _row(b, plate="Y", plate_well="A1"), _row(c, plate="X", plate_well="A2"),
    ])

    response = _upload(client, prep.id, content, insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.id}")
    assert _plates(session, prep.lab_prep) == {
        f"P-{prep.name}-X": {0: a.id, 1: c.id},
        f"P-{prep.name}-Y": {0: b.id},
    }


def test_numeric_plate_names_are_integers(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    """Excel stores plate 1 as a number; legacy named the plate ``P-<prep>-1`` (int(plate))."""
    a, b, _ = prep.libraries
    _upload(client, prep.id, _xlsx([_row(a, plate=1, plate_well="A1"), _row(b, plate=2, plate_well="A1")]), insider_token)

    assert sorted(_plates(session, prep.lab_prep)) == [f"P-{prep.name}-1", f"P-{prep.name}-2"]


def test_reupload_replaces_plates(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    a, b, _ = prep.libraries
    _upload(client, prep.id, _xlsx([_row(a, plate="X", plate_well="A1")]), insider_token)
    old_plate_ids = [plate.id for plate in _reload(session, prep.lab_prep).plates]

    _upload(client, prep.id, _xlsx([_row(b, plate="Y", plate_well="C3")]), insider_token)

    assert _plates(session, prep.lab_prep) == {f"P-{prep.name}-Y": {26: b.id}}
    # The old plates are deleted, not just unlinked.
    for plate_id in old_plate_ids:
        assert session.first(Q.plate.select(id=plate_id)) is None


def test_unused_template_rows_create_no_plate(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    """The downloaded template has a row per well; rows without a library are ignored."""
    a = prep.libraries[0]
    content = _xlsx([
        _row(a, plate="1", plate_well="A1"),
        {"plate_well": "B1", "index_well": "B1"},
        {"plate_well": "C1", "index_well": "C1"},
    ])

    response = _upload(client, prep.id, content, insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.id}")
    assert _plates(session, prep.lab_prep) == {f"P-{prep.name}-1": {0: a.id}}


def test_blank_rows_do_not_shift_values(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    """Fully blank rows between libraries are dropped; the following rows keep their own values."""
    a, b, c = prep.libraries
    content = _xlsx([
        _row(a, plate="1", plate_well="A1"),
        {},
        _row(b, plate="1", plate_well="b2", lib_conc_ng_ul=1.5),
        {},
        {},
        _row(c, plate="2", plate_well="c3"),
    ])

    response = _upload(client, prep.id, content, insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.id}")
    assert _plates(session, prep.lab_prep) == {
        f"P-{prep.name}-1": {0: a.id, 13: b.id},
        f"P-{prep.name}-2": {26: c.id},
    }
    session.expire_all()
    assert session.get_one(Q.library.select(id=b.id)).qubit_concentration == 1.5


def test_plate_column_is_optional(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    a, b, _ = prep.libraries
    columns = [col for col in COLUMNS if col != "plate"]

    response = _upload(client, prep.id, _xlsx([_row(a, plate_well="A1"), _row(b, plate_well="A2")], columns=columns), insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.id}")
    assert _plates(session, prep.lab_prep) == {f"P-{prep.name}": {0: a.id, 1: b.id}}


def test_pool_x_marks_library_failed(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    a, b, _ = prep.libraries
    statuses = {lib.id: lib.status for lib in prep.libraries}

    _upload(client, prep.id, _xlsx([_row(a, pool=" X ", plate_well="A1"), _row(b, pool="1", plate_well="A2")]), insider_token)

    session.expire_all()
    assert session.get_one(Q.library.select(id=a.id)).status == C.LibraryStatus.FAILED
    assert session.get_one(Q.library.select(id=b.id)).status == statuses[b.id]


def test_lib_conc_sets_qubit_concentration(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    a, b, _ = prep.libraries

    response = _upload(client, prep.id, _xlsx([
        _row(a, plate_well="A1", lib_conc_ng_ul=2.5),
        _row(b, plate_well="A2"),
    ]), insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.id}")
    session.expire_all()
    assert session.get_one(Q.library.select(id=a.id)).qubit_concentration == 2.5
    assert session.get_one(Q.library.select(id=b.id)).qubit_concentration is None


# ── Submit: validation ──────────────────────────────────────────────────────


def _assert_unchanged(session: SyncSession, prep: Prep) -> None:
    lab_prep = _reload(session, prep.lab_prep)
    assert lab_prep.prep_file is None
    assert lab_prep.plates == []


def test_missing_file_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    response = _upload(client, prep.id, None, insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, prep)


def test_library_not_in_prep_is_rejected(
    client: TestClient, session: SyncSession, prep: Prep, user, insider_token: str,
):
    other = create_library(session, user, create_seq_request(session, user))
    session.commit()

    response = _upload(client, prep.id, _xlsx([_row(other, plate_well="A1")]), insider_token)

    assert_form_invalid(response, f"Library ID '{other.id}' is not part of this prep.")
    _assert_unchanged(session, prep)


def test_library_name_mismatch_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    a, b, _ = prep.libraries
    response = _upload(client, prep.id, _xlsx([{"library_id": a.id, "library_name": b.name, "plate_well": "A1"}]), insider_token)

    assert_form_invalid(response, f"does not match the existing library name '{a.name}'")
    _assert_unchanged(session, prep)


def test_missing_library_name_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    response = _upload(client, prep.id, _xlsx([{"library_id": prep.libraries[0].id, "plate_well": "A1"}]), insider_token)

    assert_form_invalid(response, "Library Name is required when Library ID is provided")
    _assert_unchanged(session, prep)


def test_duplicate_plate_well_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    a, b, _ = prep.libraries
    response = _upload(client, prep.id, _xlsx([_row(a, plate_well="A1"), _row(b, plate_well="a1")]), insider_token)

    assert_form_invalid(response, "Plate Well+plate 'A1' is duplicated.")
    _assert_unchanged(session, prep)


@pytest.mark.parametrize("blank", [None, "", "  "])
def test_blank_plate_well_is_rejected(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str, blank: str | None,
):
    """Blank wells are reported as missing, not as duplicates of 'nan'."""
    a, b, _ = prep.libraries
    response = _upload(client, prep.id, _xlsx([_row(a, plate_well=blank), _row(b, plate_well=blank)]), insider_token)

    assert_form_invalid(response, "Plate Well is required.")
    assert "duplicated" not in response.text
    _assert_unchanged(session, prep)


def test_same_well_on_different_plates_is_allowed(client: TestClient, prep: Prep, insider_token: str):
    a, b, _ = prep.libraries
    response = _upload(client, prep.id, _xlsx([_row(a, plate="X", plate_well="A1"), _row(b, plate="Y", plate_well="A1")]), insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.id}")


@pytest.mark.parametrize("well", ["A13", "I1", "Z99", "foo"])
def test_invalid_plate_well_is_rejected(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str, well: str,
):
    """Wells outside the 8x12 plate must not be saved (A13 would otherwise land on B1)."""
    response = _upload(client, prep.id, _xlsx([_row(prep.libraries[0], plate_well=well)]), insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, prep)


def test_non_numeric_concentration_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    response = _upload(client, prep.id, _xlsx([_row(prep.libraries[0], plate_well="A1", lib_conc_ng_ul="lots")]), insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, prep)


def test_missing_prep_table_sheet_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    content = _xlsx([_row(prep.libraries[0], plate_well="A1")], sheet_name="Sheet1")

    response = _upload(client, prep.id, content, insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, prep)


def test_unsupported_file_type_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    response = _upload(client, prep.id, b"hello", insider_token, filename="prep.txt")

    assert_form_invalid(response, "File type '.txt' is not allowed.")
    _assert_unchanged(session, prep)


def test_corrupt_xlsx_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    response = _upload(client, prep.id, b"not a spreadsheet", insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, prep)


def test_invalid_upload_keeps_existing_plates_and_file(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    a, b, _ = prep.libraries
    _upload(client, prep.id, _xlsx([_row(a, plate_well="A1")]), insider_token)
    before = _plates(session, prep.lab_prep)
    prep_file = _reload(session, prep.lab_prep).prep_file
    assert prep_file is not None
    uuid_before = prep_file.uuid

    response = _upload(client, prep.id, _xlsx([_row(a, plate_well="A1"), _row(b, plate_well="A1")]), insider_token)

    assert_form_invalid(response)
    assert _plates(session, prep.lab_prep) == before
    prep_file = _reload(session, prep.lab_prep).prep_file
    assert prep_file is not None and prep_file.uuid == uuid_before


def test_empty_spreadsheet_is_rejected(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    """Legacy: 'Spreadsheet is empty.'"""
    response = _upload(client, prep.id, _xlsx([]), insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, prep)


@pytest.mark.parametrize("missing", ["library_id", "library_name", "pool", "plate_well"])
def test_missing_column_is_rejected(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str, missing: str,
):
    """Legacy: "Column '<label>' is missing in the spreadsheet." for every non-optional column."""
    columns = [col for col in COLUMNS if col != missing]
    row = {k: v for k, v in _row(prep.libraries[0], plate_well="A1", pool="1").items() if k != missing}

    response = _upload(client, prep.id, _xlsx([row], columns=columns), insider_token)

    assert_form_invalid(response, missing)
    _assert_unchanged(session, prep)


def test_missing_optional_plate_column_is_accepted(client: TestClient, session: SyncSession, prep: Prep, insider_token: str):
    columns = [col for col in COLUMNS if col != "plate"]
    a = prep.libraries[0]

    response = _upload(client, prep.id, _xlsx([_row(a, plate_well="A1")], columns=columns), insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.id}")
    assert _plates(session, prep.lab_prep) == {f"P-{prep.name}": {0: a.id}}
