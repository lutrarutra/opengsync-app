"""ReindexWorkflow from a lab prep: the barcode table is prefilled from the prep table.

As legacy ``CommonBarcodeInputForm`` (reindex branch): for libraries without a
stored barcode, index well, kit and name come from the lab prep's uploaded prep
file (``prep_table`` sheet). Libraries that already have a barcode keep it.

The prep table holds several indices per library as ``;``-separated values; the
barcode table has one row per index, so they are unaggregated (a single value,
e.g. one kit for all indices, applies to every row).
"""

import json
import os
import uuid
from pathlib import Path

import pandas as pd
import pytest

from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import config, redis
from server.forms.workflows.reindex.ReindexWorkflow import ReindexWorkflow

from ...db.create_units import create_index_kit, create_lab_prep, create_library, create_seq_request
from .._http import OpenGSyncTestClient, post_form

PREFIX = "/htmx/workflows/reindex"
COLUMNS = ["index_well", "kit_i7", "name_i7", "kit_i5", "name_i5"]


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


def _library_in_prep(session: SyncSession, user: models.User, lab_prep: models.LabPrep) -> models.Library:
    library = create_library(session, user, create_seq_request(session, user))
    library.lab_prep_id = lab_prep.id
    session.save(library, flush=True)
    return library


def _barcode_rows(
    client: OpenGSyncTestClient, token: str, lab_prep: models.LabPrep, library: models.Library,
) -> list[dict]:
    """Run the select step and return the library's rows of the saved barcode table."""
    workflow_uuid = str(uuid.uuid4())
    response = post_form(
        client, f"{PREFIX}/select-samples",
        {"selected_library_ids": json.dumps([library.id])},
        token=token, params={"uuid": workflow_uuid, "lab_prep_id": lab_prep.id},
    )
    assert response.status_code == 200, response.text

    workflow = ReindexWorkflow(step=None, r=redis.RedisClient(pool=client.app.state.redis_pool), uuid=workflow_uuid)  # type: ignore[arg-type]  # resume at the last step
    table = workflow.tables["barcode_table"]
    rows = table[table["library_id"] == library.id][COLUMNS]
    return [{col: (None if pd.isna(v) else v) for col, v in row.items()} for row in rows.to_dict("records")]


def test_unindexed_library_is_prefilled_from_prep_table(
    client: OpenGSyncTestClient, session: SyncSession, user, insider, insider_token: str, media_folder: Path,
):
    lab_prep = create_lab_prep(session, insider)
    library = _library_in_prep(session, user, lab_prep)
    kit7, kit5 = create_index_kit(session), create_index_kit(session)
    _attach_prep_file(session, lab_prep, media_folder, [{
        "library_id": library.id, "library_name": library.name,
        "index_well": " H11 ", "kit_i7": f"#{kit7.identifier}", "name_i7": "PREP_I7",
        "kit_i5": kit5.identifier, "name_i5": "PREP_I5",
    }])
    session.commit()

    rows = _barcode_rows(client, insider_token, lab_prep, library)

    # Whitespace stripped and the '#' removed from the kit, as legacy did.
    assert rows == [{
        "index_well": "H11", "kit_i7": kit7.identifier, "name_i7": "PREP_I7",
        "kit_i5": kit5.identifier, "name_i5": "PREP_I5",
    }]


def test_semicolon_separated_prep_values_become_one_row_per_index(
    client: OpenGSyncTestClient, session: SyncSession, user, insider, insider_token: str, media_folder: Path,
):
    lab_prep = create_lab_prep(session, insider)
    library = _library_in_prep(session, user, lab_prep)
    kit = create_index_kit(session)
    _attach_prep_file(session, lab_prep, media_folder, [{
        "library_id": library.id, "library_name": library.name,
        "index_well": "H11;H12", "kit_i7": kit.identifier, "name_i7": "PREP_A;PREP_B",
        "kit_i5": None, "name_i5": "PREP_X; PREP_Y",
    }])
    session.commit()

    rows = _barcode_rows(client, insider_token, lab_prep, library)

    # Wells and names are paired by position; the single kit applies to both indices.
    assert rows == [
        {"index_well": "H11", "kit_i7": kit.identifier, "name_i7": "PREP_A", "kit_i5": None, "name_i5": "PREP_X"},
        {"index_well": "H12", "kit_i7": kit.identifier, "name_i7": "PREP_B", "kit_i5": None, "name_i5": "PREP_Y"},
    ]


def test_indexed_library_keeps_its_stored_barcode(
    client: OpenGSyncTestClient, session: SyncSession, user, insider, insider_token: str, media_folder: Path,
):
    lab_prep = create_lab_prep(session, insider)
    library = _library_in_prep(session, user, lab_prep)
    library.indices.append(models.LibraryIndex(name_i7="STORED_I7", sequence_i7="ACGTACGTAA"))
    session.save(library, flush=True)
    kit = create_index_kit(session)
    _attach_prep_file(session, lab_prep, media_folder, [{
        "library_id": library.id, "library_name": library.name,
        "index_well": "G10", "kit_i7": kit.identifier, "name_i7": "PREP_I7",
        "kit_i5": None, "name_i5": None,
    }])
    session.commit()

    rows = _barcode_rows(client, insider_token, lab_prep, library)

    assert rows == [{"index_well": None, "kit_i7": None, "name_i7": "STORED_I7", "kit_i5": None, "name_i5": None}]


def test_without_prep_file_nothing_is_prefilled(
    client: OpenGSyncTestClient, session: SyncSession, user, insider, insider_token: str, media_folder: Path,
):
    lab_prep = create_lab_prep(session, insider)
    library = _library_in_prep(session, user, lab_prep)
    session.commit()

    rows = _barcode_rows(client, insider_token, lab_prep, library)

    assert rows == [{col: None for col in COLUMNS}]


def test_library_missing_from_prep_table_is_left_empty(
    client: OpenGSyncTestClient, session: SyncSession, user, insider, insider_token: str, media_folder: Path,
):
    lab_prep = create_lab_prep(session, insider)
    library = _library_in_prep(session, user, lab_prep)
    other = _library_in_prep(session, user, lab_prep)
    _attach_prep_file(session, lab_prep, media_folder, [{
        "library_id": other.id, "library_name": other.name,
        "index_well": "A1", "kit_i7": None, "name_i7": "OTHER", "kit_i5": None, "name_i5": None,
    }])
    session.commit()

    rows = _barcode_rows(client, insider_token, lab_prep, library)

    assert rows == [{col: None for col in COLUMNS}]
