"""Spreadsheet error messages name the columns as the user sees them, in row order.

Customer test 2026-11-04: errors said 'sample_id', 'sample_name' and 'genome_id' instead of the headers
'Sample Name' and 'Organism', were not sorted by row, and a partly filled attribute column only said
"Missing value" without naming the column.
"""
import html
import re

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_seq_request
from ..._http import spreadsheet_payload
from ._workflow import AnnotationWorkflow, HUMAN, MOUSE


def _errors(response) -> list[str]:
    return [html.unescape(e) for e in re.findall(r"(Row \d+: [^<]+)", response.text)]


def _workflow(client, session: SyncSession, user, token: str) -> AnnotationWorkflow:
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf = AnnotationWorkflow(client, token, seq_request.id)
    wf.begin()
    wf.project("Spreadsheet messages")
    return wf


def test_sample_errors_use_headers_and_row_order(client, session: SyncSession, user, user_token):
    wf = _workflow(client, session, user, user_token)
    response = wf.post("sample-annotation", spreadsheet_payload(["Sample Name", "Organism"], [
        ["dup_sample", MOUSE], ["dup_sample", MOUSE], ["no_organism", ""], ["bad_organism", "mouse"],
    ]), status=202, next_step="sample-annotation")

    errors = _errors(response)
    assert errors, response.text
    text = " ".join(errors)
    for internal in ("sample_id", "sample_name", "genome_id"):
        assert f"'{internal}'" not in text
    assert "'Sample Name'" in text and "'Organism'" in text
    rows = [int(re.match(r"Row (\d+)", e).group(1)) for e in errors]
    assert rows == sorted(rows)


def test_partly_filled_attribute_column_names_the_column(client, session: SyncSession, user, user_token):
    wf = _workflow(client, session, user, user_token)
    wf.samples([["attr_a", HUMAN], ["attr_b", HUMAN]])
    response = wf.post("sample-attribute-annotation", spreadsheet_payload(
        ["Sample", "Disease"], [["attr_a [new]", "NASH"], ["attr_b [new]", ""]],
    ), status=202, next_step="sample-attribute-annotation")

    assert any("Missing value for 'Disease'" in e and "NA" in e for e in _errors(response)), _errors(response)


def test_invalid_characters_in_sample_name_are_reported_not_dropped(client, session: SyncSession, user, user_token):
    wf = _workflow(client, session, user, user_token)
    response = wf.post("sample-annotation", spreadsheet_payload(["Sample Name", "Organism"], [
        ["<b>x</b>", HUMAN], ["liver ko-1", HUMAN],
    ]), status=202, next_step="sample-annotation")

    errors = _errors(response)
    assert any(e.startswith("Row 1:") and "Invalid character in name: '<'" in e for e in errors), errors
    assert not any("too short" in e for e in errors), errors
    assert not any(e.startswith("Row 2:") for e in errors), errors  # spaces and dashes become '_'


def test_sex_attribute_is_normalized():
    from server.forms.workflows.library_annotation.SampleAttributeAnnotationForm import _normalize_sex
    assert [_normalize_sex(v) for v in ["F", "female", " Male ", "m", "unknown"]] == ["female", "female", "male", "male", "unknown"]



def test_cell_values_cannot_end_the_spreadsheet_script(client, session: SyncSession, user, user_token):
    """Sheet data was the Python repr of the rows inside <script>: a cell '</script><img onerror=...>' ran
    script when the sheet was shown again (customer test 2026-11-04)."""
    payload = "</script><img src=x onerror=alert(1)>"
    wf = _workflow(client, session, user, user_token)
    wf.samples([["script_a", HUMAN], ["script_b", HUMAN]])
    response = wf.post("sample-attribute-annotation", spreadsheet_payload(
        ["Sample", "Disease"], [["script_a [new]", payload], ["script_b [new]", ""]],
    ), status=202, next_step="sample-attribute-annotation")

    assert "</script><img" not in response.text
    from ._workflow import spreadsheet_rows
    assert any(payload in row for row in spreadsheet_rows(response))
