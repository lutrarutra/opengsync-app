"""Customer-facing copy and empty states (customer test 2026-11-04)."""
import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, categories as C

from ..db.create_units import create_seq_request
from ._http import get


def test_fresh_customer_sees_empty_states(client: TestClient, user_token: str):
    assert "No sequencing requests yet" in get(client, "/htmx/seq_requests/render-feed", user_token, htmx=True).text
    assert "No projects yet" in get(client, "/htmx/projects/render-feed", user_token, htmx=True).text
    for path in ("/htmx/seq_requests/render-table-page", "/htmx/groups/render-table-page"):
        assert "No entries to show." in get(client, path, user_token, htmx=True).text


def test_layout_step_is_not_called_optional_before_samples_are_added(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    checklist = get(client, f"/htmx/seq_requests/{seq_request.id}/submit-checklist", user_token, htmx=True).text
    assert "Specify Sample Submission Layout (Optional)" not in checklist
    assert "Add samples to the request first." in checklist
    # no workflow tile applies to a customer's raw-sample request: point to the checklist instead
    assert "There are no workflows for this kind of request" in get(client, f"/seq_requests/{seq_request.id}", user_token).text


@pytest.mark.parametrize("submission_type, wording", [
    (C.SubmissionType.RAW_SAMPLES, "Add Samples to the Request"),
    (C.SubmissionType.POOLED_LIBRARIES, "Add Libraries to the Request"),
])
def test_checklist_names_what_is_added(client: TestClient, session: SyncSession, user, user_token: str, submission_type, wording: str):
    seq_request = create_seq_request(session, user, submission_type=submission_type)
    session.commit()
    assert wording in get(client, f"/htmx/seq_requests/{seq_request.id}/submit-checklist", user_token, htmx=True).text


def test_none_renders_empty(client: TestClient):
    """Unset values render as empty text, never as "None" (review panel, BA fragment sizes)."""
    from server.core.templates import j2

    rendered = j2.env.from_string("<p>{{ value }} bp</p><p>{{ value | tojson }}</p>").render(value=None)

    assert rendered == "<p> bp</p><p>null</p>"


def test_multiselect_filter_ids_are_unique_per_table(client: TestClient):
    """The same column filter on the page and in a modal table used to share checkbox ids, so a
    label click toggled the hidden checkbox behind the modal."""
    import re
    from server.core.templates import j2

    template = j2.env.from_string(
        '{% from "components/multi_select.jinja2" import multi_select2 %}'
        '{{ multi_select2(choices, "status", id_prefix="library-table-") }}'
        '{{ multi_select2(choices, "status", id_prefix="select-libraries-table-") }}'
    )
    html = template.render(choices=[(1, "Draft"), (2, "Submitted")])

    ids = re.findall(r'<input[^>]*\bid="([^"]+)"', html)
    assert len(ids) == 6 and len(set(ids)) == len(ids)
    for checkbox_id in ids:
        assert f'for="{checkbox_id}"' in html


def test_table_col_prefixes_filter_ids_with_its_container(client: TestClient):
    from pathlib import Path
    from server.core.templates import j2

    source = Path(j2.env.loader.searchpath[0]) / "components" / "table_col.jinja2"  # type: ignore[union-attr]
    assert 'id_prefix=table_container_id ~ "-"' in source.read_text()


@pytest.mark.parametrize("filter_values, query, hinted", [
    ({}, None, False),
    ({"status": [1]}, None, True),
    ({}, "carol", True),
])
def test_empty_table_hints_at_active_filters(client: TestClient, filter_values, query, hinted: bool):
    """Pickers open with a default status filter (e.g. lab-prep BA: 'Preparing'); an empty result must say so."""
    from types import SimpleNamespace
    from server.core.templates import j2

    table = SimpleNamespace(num_pages=0, active_page=0, filter_values=filter_values, active_query_value=query)
    html = j2.env.from_string(
        '{% from "components/pagination.jinja2" import pagination %}{{ pagination("t", table) }}'
    ).render(table=table)

    assert "No entries to show." in html
    assert ("Filters or a search are active" in html) is hinted
