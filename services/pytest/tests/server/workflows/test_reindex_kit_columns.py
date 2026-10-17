"""ReindexWorkflow: the kit columns are QueryColumns, their cells hold index kit ids.

Submitting kit ids (or identifiers, as in an uploaded prep table) is accepted, 'Back' refills the kits by id, and an
invalid submission is rendered again with the cells as submitted.
"""

from typing import Any

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C

from .._http import get
from ._spreadsheet import query_labels
from .library_annotation._workflow import create_dual_index_kit, create_tenx_atac_index_kit, spreadsheet_records
from .test_reindex import ATAC_COLUMNS, ATAC_SEQUENCES, BARCODE_COLUMNS, KIT_WELLS, Run, _index_type, _indices, _kit_label, _label, _url, atac, run  # noqa: F401

UNKNOWN_ID = 999_999_999


def _records(columns: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row)) for row in rows]


def _shown(response, columns: list[str]) -> list[dict[str, Any]]:
    return [{title: record[title] for title in columns} for record in spreadsheet_records(response)]


def test_barcode_kits_by_id(client: TestClient, session: SyncSession, run: Run, user_token: str):
    kit = create_dual_index_kit(session, "RIDX_COL", "Reindex Column Kit", KIT_WELLS)
    atac_kit = create_tenx_atac_index_kit(session, "RIDX_COL_ATAC", "Reindex Column ATAC Kit", {"A1": ("SI-NA-A1", ATAC_SEQUENCES)})
    response = run.select(client, user_token, [run.a, run.b])
    assert "/htmx/index_kits/query?type_in=" in response.text

    valid = [[_label(run.a), "A1", kit.id, "", "", kit.id, "", ""], [_label(run.b), "B1", kit.id, "", "", kit.id, "", ""]]
    for rows, error in [
        ([valid[0], [_label(run.b), "B1", UNKNOWN_ID, "", "", "", "", ""]], "Unknown i7 kit"),  # validation
        ([valid[0], [_label(run.b), "B1", atac_kit.id, "", "", "", "", ""]], "Unknown i7 kit"),  # not an i7 kit
        ([valid[0], [_label(run.b), "H12", kit.id, "", "", "", "", ""]], "not found in kit"),  # route
    ]:
        response = run.barcodes(client, user_token, rows)
        assert response.status_code == 202 and error in response.text, error
        assert _shown(response, BARCODE_COLUMNS) == _records(BARCODE_COLUMNS, rows), error

    # Identifiers are resolved to the kit
    response = run.barcodes(client, user_token, [[*row[:2], kit.identifier, *row[3:5], kit.identifier, *row[6:]] for row in valid])
    assert response.status_code == 200, response.text

    back = get(client, _url(client, "BarcodeInputForm.Previous"), user_token, params=run.params)
    assert back.status_code == 200, back.text
    assert [[r["Library"], r["Index Well"], r["i7 Kit"], r["i5 Kit"]] for r in _shown(back, BARCODE_COLUMNS)] == [
        [_label(run.a), "A1", kit.id, kit.id], [_label(run.b), "B1", kit.id, kit.id],
    ]
    assert query_labels(back, "i7 Kit") == {kit.id: _kit_label(kit)}

    assert run.barcodes(client, user_token, valid).status_code == 200
    run.complete(client, user_token)
    assert [(i[0], i[4]) for i in _indices(session, run.b)] == [("D702", kit.id)]


def test_atac_kits_by_id(client: TestClient, session: SyncSession, run: Run, atac: models.Library, user_token: str):
    kit = create_tenx_atac_index_kit(session, "RIDX_COL_ATAC", "Reindex Column ATAC Kit", {"A1": ("SI-NA-A1", ATAC_SEQUENCES)})
    dual = create_dual_index_kit(session, "RIDX_COL", "Reindex Column Kit", KIT_WELLS)
    run.select(client, user_token, [atac])

    valid = [[_label(atac), "A1", kit.id, "", "", "", "", ""]]
    for rows, error in [
        ([[_label(atac), "A1", dual.id, "", "", "", "", ""]], "Unknown kit"),  # not an ATAC kit
        ([[_label(atac), "H12", kit.id, "", "", "", "", ""]], "not found in kit"),  # route
    ]:
        response = run.atac(client, user_token, rows)
        assert response.status_code == 202 and error in response.text, error
        assert _shown(response, ATAC_COLUMNS) == _records(ATAC_COLUMNS, rows), error

    assert run.atac(client, user_token, valid).status_code == 200
    back = get(client, _url(client, "TENXATACBarcodeInputForm.Previous"), user_token, params=run.params)
    assert back.status_code == 200, back.text
    assert [[r["Library"], r["Kit"], r["Name"]] for r in _shown(back, ATAC_COLUMNS)] == [[_label(atac), kit.id, "SI-NA-A1"]]
    assert query_labels(back, "Kit") == {kit.id: _kit_label(kit)}

    assert run.atac(client, user_token, valid).status_code == 200
    run.complete(client, user_token)
    assert {i[4] for i in _indices(session, atac)} == {kit.id}
    assert _index_type(session, atac) == C.IndexType.TENX_ATAC_INDEX
