"""Exports must not turn customer text into spreadsheet formulas (customer test 2026-11-04).

A description or attribute like ``=HYPERLINK(...)`` was written as a formula into the .xlsx exports and as is
into the TSV, both opened by staff in Excel. Workbooks keep the value as text (unchanged); CSV/TSV get a
leading ' only on values that would start a formula ('-' is left alone: negative numbers).
"""
import io

import openpyxl
import pandas as pd
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models

from ..db.create_units import create_lab_prep, create_library, create_pool, create_project, create_seq_request
from ._http import get

FORMULA = '=HYPERLINK("http://evil.example","x")'


def test_request_workbook_keeps_formula_like_text_as_text(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user)
    seq_request.description = FORMULA
    create_library(session, user, seq_request)
    session.commit()

    workbook = openpyxl.load_workbook(io.BytesIO(get(client, f"/htmx/seq_requests/{seq_request.id}/export", user_token).content))
    cells = [c for ws in workbook.worksheets for row in ws.iter_rows() for c in row if c.value == FORMULA]
    assert cells and all(c.data_type == "s" for c in cells)


def test_project_workbook_keeps_formula_like_text_as_text(client: TestClient, session: SyncSession, user, user_token: str):
    project = create_project(session, user)
    project.title = FORMULA
    session.commit()

    workbook = openpyxl.load_workbook(io.BytesIO(get(client, f"/htmx/projects/{project.id}/export", user_token).content))
    assert not [c for ws in workbook.worksheets for row in ws.iter_rows() for c in row if c.data_type == "f"]
    assert any(c.value == FORMULA for ws in workbook.worksheets for row in ws.iter_rows() for c in row)


def test_library_tsv_neutralizes_formulas(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    library.pool_id = create_pool(session, user, seq_request).id  # the export lists pooled, indexed libraries
    session.save(models.LibraryIndex(library_id=library.id, name_i7="=1+1", sequence_i7="ACGTACGT"), flush=True)
    session.commit()

    response = get(client, f"/htmx/seq_requests/{seq_request.id}/export-libraries", user_token)
    df = pd.read_csv(io.StringIO(response.text), sep="\t")
    assert "'=1+1" in df.values
    assert "=1+1" not in df.values


def test_neutralize_formulas_leaves_other_values_alone():
    from server.utils.io import neutralize_formulas
    df = pd.DataFrame({"a": ["=x", "+x", "@x", "-5", "lib_1", None], "n": [1, -2, 3, 4, 5, 6]})
    out = neutralize_formulas(df)
    assert out["a"].tolist()[:5] == ["'=x", "'+x", "'@x", "-5", "lib_1"] and out["a"].isna().iloc[5]
    assert out["n"].tolist() == [1, -2, 3, 4, 5, 6]
    assert df["a"].iloc[0] == "=x"  # input not modified


def test_prep_template_writes_customer_names_as_text(
    client: TestClient, session: SyncSession, user, insider, insider_token: str,
):
    """The requestor's name goes into the prep template; the template's own formulas must survive."""
    user.first_name = FORMULA
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    lab_prep = create_lab_prep(session, insider)
    library.lab_prep_id = lab_prep.id
    session.commit()

    response = get(client, f"/htmx/lab_preps/{lab_prep.id}/prep-spreadsheet-template", insider_token)

    assert response.status_code == 200
    sheet = openpyxl.load_workbook(io.BytesIO(response.content))["prep_table"]
    cells = [c for row in sheet.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith(FORMULA)]
    assert cells and all(c.data_type == "s" for c in cells)
