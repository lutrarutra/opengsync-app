"""LibraryPoolingWorkflow: the pooling spreadsheet is prefilled from the lab prep's prep table.

As legacy ``LibraryPoolingForm``: when libraries have no pool yet, the rows are
ordered like the uploaded prep file (``prep_table`` sheet) and the pool column
is taken from it, with a ``<lab_prep.name>_`` prefix stripped.

The prep table may hold several rows for one library (one row per index), so
library IDs in it are not unique.
"""

import os
import uuid
from pathlib import Path

import pandas as pd
import pytest

from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import config

from ...db.create_units import create_lab_prep, create_library, create_seq_request
from .._http import OpenGSyncTestClient, get
from .library_annotation._workflow import spreadsheet_rows

PREFIX = "/htmx/workflows/library-pooling"


@pytest.fixture
def media_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config.settings.app_config, "media_folder", str(tmp_path))
    return tmp_path


def _attach_prep_file(session: SyncSession, lab_prep: models.LabPrep, media_folder: Path, rows: list[dict]) -> None:
    media_file = session.save(Q.media_file.create(
        name="prep", type=C.MediaFileType.LIBRARY_PREP_FILE, extension=".xlsx",
        uploader_id=lab_prep.creator_id, size_bytes=1, uuid=str(uuid.uuid4()), lab_prep_id=lab_prep.id,
    ), flush=True)
    path = media_folder / media_file.path
    os.makedirs(path.parent, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, sheet_name="prep_table", index=False)


def _library_in_prep(session: SyncSession, user: models.User, lab_prep: models.LabPrep, seq_request) -> models.Library:
    library = create_library(session, user, seq_request)
    library.lab_prep_id = lab_prep.id
    session.save(library, flush=True)
    return library


def _begin(client: OpenGSyncTestClient, token: str, lab_prep: models.LabPrep):
    response = get(client, f"{PREFIX}/begin", token, params={"lab_prep_id": lab_prep.id})
    assert response.status_code == 200, response.text
    return response


def _id_pool_rows(response) -> list[tuple[int, str]]:
    """(library_id, pool) per spreadsheet row; columns are library ("name [id]"), pool, M reads requested."""
    return [(int(row[0].rpartition(" [")[2].rstrip("]")), row[1] or "") for row in spreadsheet_rows(response)]


def test_rows_follow_prep_table_order_and_take_its_pool(
    client: OpenGSyncTestClient, session: SyncSession, user, insider, insider_token: str, media_folder: Path,
):
    lab_prep = create_lab_prep(session, insider)
    seq_request = create_seq_request(session, user)
    first = _library_in_prep(session, user, lab_prep, seq_request)
    second = _library_in_prep(session, user, lab_prep, seq_request)
    _attach_prep_file(session, lab_prep, media_folder, [
        {"library_id": second.id, "library_name": second.name, "pool": f"{lab_prep.name}_B"},
        {"library_id": first.id, "library_name": first.name, "pool": 1},
    ])
    session.commit()

    response = _begin(client, insider_token, lab_prep)

    assert _id_pool_rows(response) == [(second.id, "B"), (first.id, "1")]


def test_prep_table_with_one_row_per_index_does_not_crash(
    client: OpenGSyncTestClient, session: SyncSession, user, insider, insider_token: str, media_folder: Path,
):
    """Regression: duplicate library IDs raised 'Categorical categories must be unique'.

    Each library is shown once, at its first position in the prep table, and gets
    the first pool given on any of its rows.
    """
    lab_prep = create_lab_prep(session, insider)
    seq_request = create_seq_request(session, user)
    first = _library_in_prep(session, user, lab_prep, seq_request)
    second = _library_in_prep(session, user, lab_prep, seq_request)
    rows = []
    for library, pool in ((second, "2"), (first, "1")):
        rows.append({"library_id": library.id, "library_name": library.name, "index_well": "A1", "pool": pool})
        for well in ("A2", "A3", "A4"):  # pool only on the first index row
            rows.append({"library_id": library.id, "library_name": library.name, "index_well": well, "pool": None})
    _attach_prep_file(session, lab_prep, media_folder, rows)
    session.commit()

    response = _begin(client, insider_token, lab_prep)

    assert _id_pool_rows(response) == [(second.id, "2"), (first.id, "1")]


def test_library_missing_from_prep_table_keeps_its_id(
    client: OpenGSyncTestClient, session: SyncSession, user, insider, insider_token: str, media_folder: Path,
):
    """A library of the prep that is not in the prep file is listed last, with its ID and no pool."""
    lab_prep = create_lab_prep(session, insider)
    seq_request = create_seq_request(session, user)
    listed = _library_in_prep(session, user, lab_prep, seq_request)
    missing = _library_in_prep(session, user, lab_prep, seq_request)
    _attach_prep_file(session, lab_prep, media_folder, [
        {"library_id": listed.id, "library_name": listed.name, "pool": "1"},
    ])
    session.commit()

    response = _begin(client, insider_token, lab_prep)

    assert _id_pool_rows(response) == [(listed.id, "1"), (missing.id, "")]


def test_outdated_ids_are_mapped_by_name_with_one_row_per_index(
    client: OpenGSyncTestClient, session: SyncSession, user, insider, insider_token: str, media_folder: Path,
):
    """Wrong IDs fall back to mapping by name; repeated names of one library's index rows don't block it."""
    lab_prep = create_lab_prep(session, insider)
    seq_request = create_seq_request(session, user)
    first = _library_in_prep(session, user, lab_prep, seq_request)
    second = _library_in_prep(session, user, lab_prep, seq_request)
    rows = []
    for stale_id, library, pool in ((900_002, second, "2"), (900_001, first, "1")):
        for well in ("A1", "A2"):
            rows.append({"library_id": stale_id, "library_name": library.name, "index_well": well, "pool": pool})
    _attach_prep_file(session, lab_prep, media_folder, rows)
    session.commit()

    response = _begin(client, insider_token, lab_prep)

    assert _id_pool_rows(response) == [(second.id, "2"), (first.id, "1")]
