"""SampleAttributeTableAction: render, permissions, attribute edits, and validation.

The spreadsheet submits display-name headers. Predefined columns ("Sex", "Cell Type", ...)
map back to the ``AttributeType`` label; any other header is lower-cased with spaces
turned into underscores and stored as a ``CUSTOM`` attribute. A predefined or existing
column that is missing from the submission counts as deleted.

Access is insider-only for GET and POST (legacy: WRITE on the project — see design
note 5 in ``docs/mirgation/migration_test_plan.md``).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

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

PREFIX = "/htmx/projects"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"

# Headers the UI always submits: ID, name, then one column per non-custom AttributeType.
BASE_COLUMNS = ["ID", "Sample Name"]
PREDEFINED_COLUMNS = [t.display_name.replace("_", " ").title() for t in C.AttributeType.as_list()[1:]]


def _path(project_id: int) -> str:
    return f"{PREFIX}/{project_id}/edit-sample-attributes"


def _payload(
    rows: list[dict[str, Any]],
    extra_columns: list[str] | None = None,
    predefined: list[str] | None = None,
) -> dict[str, str]:
    """Build a submission. Each row maps header → value; missing cells are empty."""
    columns = BASE_COLUMNS + (PREDEFINED_COLUMNS if predefined is None else predefined) + (extra_columns or [])
    return spreadsheet_payload(columns, [[row.get(col, "") for col in columns] for row in rows])


def _row(sample: models.Sample, **cells: Any) -> dict[str, Any]:
    return {"ID": sample.id, "Sample Name": sample.name, **cells}


def _reload(session: SyncSession, sample: models.Sample) -> models.Sample:
    session.expire_all()
    return session.get_one(Q.sample.select(id=sample.id))


def _attr(session: SyncSession, sample: models.Sample, key: str) -> Any:
    attribute = _reload(session, sample).get_attribute(key)
    return None if attribute is None else attribute.value


@pytest.fixture
def project_samples(session: SyncSession, user) -> tuple[models.Project, models.Sample, models.Sample]:
    project = create_project(session, user)
    sample_a = create_sample(session, user, project)
    sample_a.name = "Sample_A"
    sample_a.set_attribute("tissue", "liver", C.AttributeType.TISSUE)
    sample_a.set_attribute("batch", "b1", C.AttributeType.CUSTOM)
    sample_b = create_sample(session, user, project)
    sample_b.name = "Sample_B"
    sample_b.set_attribute("tissue", "lung", C.AttributeType.TISSUE)
    sample_b.set_attribute("batch", "b2", C.AttributeType.CUSTOM)
    session.commit()
    return project, sample_a, sample_b


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_shows_samples_and_existing_attributes(
    client: TestClient, project_samples, insider_token: str,
):
    project, _, _ = project_samples

    response = get(client, _path(project.id), insider_token)

    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text
    for text in ("Sample_A", "Sample_B", "liver", "lung", "b1", "b2", "Batch", "Cell Type"):
        assert text in response.text


def test_render_project_without_any_attributes(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    """Samples whose attribute JSON is NULL still render with the predefined columns."""
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    sample.name = "Bare_Sample"
    session.commit()

    response = get(client, _path(project.id), insider_token)

    assert response.status_code == 200
    assert "Bare_Sample" in response.text
    assert "Tissue" in response.text


def test_render_does_not_mutate_samples(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, _ = project_samples

    assert get(client, _path(project.id), insider_token).status_code == 200

    reloaded = _reload(session, sample_a)
    assert {a.name: a.value for a in reloaded.attributes} == {"tissue": "liver", "batch": "b1"}


def test_render_denies_client(client: TestClient, project_samples, user_token: str):
    """Even the project owner is denied: the FastAPI action is insider-only."""
    project, _, _ = project_samples
    assert get(client, _path(project.id), user_token).status_code == 403


def test_render_unknown_project_is_404(client: TestClient, insider_token: str):
    assert get(client, _path(999999), insider_token).status_code == 404


# ── Submit: persistence ─────────────────────────────────────────────────────


def test_submit_updates_predefined_attribute(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [
            _row(sample_a, Tissue="kidney", Batch="b1", Sex="female"),
            _row(sample_b, Tissue="lung", Batch="b2"),
        ],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert "tab=project-attributes-tab" in response.headers["HX-Redirect"]
    assert_flash(response, "Changes Saved!", category="success")

    reloaded = _reload(session, sample_a)
    tissue = reloaded.get_attribute("tissue")
    assert tissue is not None and tissue.value == "kidney"
    assert tissue.type == C.AttributeType.TISSUE
    sex = reloaded.get_attribute("sex")
    assert sex is not None and sex.value == "female"
    assert sex.type == C.AttributeType.SEX
    assert _attr(session, sample_b, "sex") is None


def test_submit_new_column_creates_custom_attribute(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [
            _row(sample_a, Tissue="liver", Batch="b1", **{"Treatment Dose": "10mg"}),
            _row(sample_b, Tissue="lung", Batch="b2", **{"Treatment Dose": "20mg"}),
        ],
        extra_columns=["Batch", "Treatment Dose"],
    ), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    dose = _reload(session, sample_a).get_attribute("treatment_dose")
    assert dose is not None and dose.value == "10mg"
    assert dose.type == C.AttributeType.CUSTOM
    assert _attr(session, sample_b, "treatment_dose") == "20mg"


def test_submit_header_matching_attribute_type_gets_that_type(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    """A new header that matches a predefined type label is typed, not CUSTOM."""
    project, sample_a, sample_b = project_samples

    # "Cell Type" is predefined; resubmitting it by its display name types it as CELL_TYPE.
    response = post_form(client, _path(project.id), _payload(
        [
            _row(sample_a, Tissue="liver", Batch="b1", **{"Cell Type": "T cell"}),
            _row(sample_b, Tissue="lung", Batch="b2", **{"Cell Type": "B cell"}),
        ],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    cell_type = _reload(session, sample_a).get_attribute("cell_type")
    assert cell_type is not None and cell_type.type == C.AttributeType.CELL_TYPE


def test_submit_empty_cell_removes_attribute(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [
            _row(sample_a, Tissue="", Batch="b1"),
            _row(sample_b, Tissue="lung", Batch="b2"),
        ],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert _attr(session, sample_a, "tissue") is None
    assert _attr(session, sample_b, "tissue") == "lung"


def test_submit_removed_column_is_deleted_from_every_sample(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    """Omitting an existing column (right-click → delete) drops it from all samples."""
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [_row(sample_a, Tissue="liver"), _row(sample_b, Tissue="lung")],
    ), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert _attr(session, sample_a, "batch") is None
    assert _attr(session, sample_b, "batch") is None
    assert _attr(session, sample_a, "tissue") == "liver"


def test_submit_renamed_column_moves_values(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    """Renaming "Batch" → "Batch Number" stores the new key and drops the old one."""
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [
            _row(sample_a, Tissue="liver", **{"Batch Number": "b1"}),
            _row(sample_b, Tissue="lung", **{"Batch Number": "b2"}),
        ],
        extra_columns=["Batch Number"],
    ), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert _attr(session, sample_a, "batch_number") == "b1"
    assert _attr(session, sample_b, "batch_number") == "b2"
    assert _attr(session, sample_a, "batch") is None


def test_submit_removing_predefined_column_no_sample_has(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    """Deleting an empty predefined column (here "Age") must not fail.

    Every predefined column is deletable, and the delete loop calls
    ``Sample.delete_sample_attribute`` for every sample, which raises ``KeyError`` when
    the sample never had that attribute. Legacy had the same loop.
    """
    project, sample_a, sample_b = project_samples
    without_age = [c for c in PREDEFINED_COLUMNS if c != "Age"]

    response = post_form(client, _path(project.id), _payload(
        [_row(sample_a, Tissue="liver", Batch="b1"), _row(sample_b, Tissue="lung", Batch="b2")],
        extra_columns=["Batch"],
        predefined=without_age,
    ), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert _attr(session, sample_a, "tissue") == "liver"


def test_submit_removing_column_only_some_samples_have(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    """Deleting a column set on one sample only must clear it there and leave the other alone."""
    project, sample_a, sample_b = project_samples
    sample_a = _reload(session, sample_a)
    sample_a.set_attribute("note", "check RIN", C.AttributeType.CUSTOM)
    session.commit()

    response = post_form(client, _path(project.id), _payload(
        [_row(sample_a, Tissue="liver", Batch="b1"), _row(sample_b, Tissue="lung", Batch="b2")],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert _attr(session, sample_a, "note") is None


# ── Submit: validation ──────────────────────────────────────────────────────


def _assert_unchanged(session: SyncSession, sample_a: models.Sample, sample_b: models.Sample) -> None:
    assert {a.name: a.value for a in _reload(session, sample_a).attributes} == {"tissue": "liver", "batch": "b1"}
    assert {a.name: a.value for a in _reload(session, sample_b).attributes} == {"tissue": "lung", "batch": "b2"}


def test_submit_unknown_sample_id_is_rejected(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [
            {"ID": 999999, "Sample Name": "Sample_A", "Tissue": "kidney", "Batch": "b1"},
            _row(sample_b, Tissue="lung", Batch="b2"),
        ],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_form_invalid(response, "Sample with ID 999999 does not exist")
    _assert_unchanged(session, sample_a, sample_b)


def test_submit_sample_from_another_project_is_rejected(
    client: TestClient, session: SyncSession, user, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples
    foreign = create_sample(session, user, create_project(session, user))
    foreign.name = "Sample_A"
    session.commit()

    response = post_form(client, _path(project.id), _payload(
        [
            {"ID": foreign.id, "Sample Name": "Sample_A", "Tissue": "kidney", "Batch": "b1"},
            _row(sample_b, Tissue="lung", Batch="b2"),
        ],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_form_invalid(response, f"Sample with ID {foreign.id} does not belong to this project")
    _assert_unchanged(session, sample_a, sample_b)
    assert _reload(session, foreign).get_attribute("tissue") is None


def test_submit_mismatched_sample_name_is_rejected(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [
            {"ID": sample_a.id, "Sample Name": "Sample_B", "Tissue": "kidney", "Batch": "b1"},
            {"ID": sample_b.id, "Sample Name": "Sample_A", "Tissue": "lung", "Batch": "b2"},
        ],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_form_invalid(response, f"Sample name does not match sample with ID {sample_a.id}")
    _assert_unchanged(session, sample_a, sample_b)


def test_submit_missing_sample_row_is_rejected(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    """Every project sample must appear in the table."""
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [_row(sample_a, Tissue="kidney", Batch="b1")],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_form_invalid(response, "missing option 'Sample_B'")
    _assert_unchanged(session, sample_a, sample_b)


def test_submit_duplicate_sample_row_is_rejected(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [
            _row(sample_a, Tissue="kidney", Batch="b1"),
            _row(sample_a, Tissue="heart", Batch="b1"),
            _row(sample_b, Tissue="lung", Batch="b2"),
        ],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, sample_a, sample_b)


def test_submit_missing_id_column_is_rejected(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples
    columns = ["Sample Name", "Tissue"]

    response = post_form(client, _path(project.id), spreadsheet_payload(
        columns, [["Sample_A", "kidney"], ["Sample_B", "lung"]],
    ), token=insider_token)

    assert_form_invalid(response, "sample_id")
    _assert_unchanged(session, sample_a, sample_b)


def test_submit_short_column_name_is_rejected(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [_row(sample_a, Batch="b1", Ab="x"), _row(sample_b, Batch="b2", Ab="y")],
        extra_columns=["Batch", "Ab"],
    ), token=insider_token)

    assert_form_invalid(response, "Column: 'ab', specify more descriptive column name")
    _assert_unchanged(session, sample_a, sample_b)


def test_submit_duplicate_column_names_are_rejected(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    """"Donor" and "donor" both normalise to the label ``donor``."""
    project, sample_a, sample_b = project_samples
    columns = BASE_COLUMNS + PREDEFINED_COLUMNS + ["Batch", "Donor", "donor"]
    tissue = PREDEFINED_COLUMNS.index("Tissue")

    def row(sample: models.Sample, tissue_value: str, batch: str) -> list[Any]:
        cells: list[Any] = [sample.id, sample.name] + [""] * len(PREDEFINED_COLUMNS) + [batch, "d1", "d2"]
        cells[len(BASE_COLUMNS) + tissue] = tissue_value
        return cells

    response = post_form(client, _path(project.id), spreadsheet_payload(
        columns, [row(sample_a, "kidney", "b1"), row(sample_b, "lung", "b2")],
    ), token=insider_token)

    assert_form_invalid(response, "Duplicate column names")
    _assert_unchanged(session, sample_a, sample_b)


def test_submit_too_long_predefined_value_is_rejected(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples
    too_long = "x" * (models.SampleAttribute.MAX_NAME_LENGTH + 1)

    response = post_form(client, _path(project.id), _payload(
        [_row(sample_a, Tissue=too_long, Batch="b1"), _row(sample_b, Tissue="lung", Batch="b2")],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_form_invalid(response, "too long")
    _assert_unchanged(session, sample_a, sample_b)


def test_submit_one_invalid_row_saves_nothing(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    """A valid edit on one row is not persisted when another row fails validation."""
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [
            _row(sample_a, Tissue="kidney", Batch="b9"),
            {"ID": sample_b.id, "Sample Name": "Sample_A", "Tissue": "lung", "Batch": "b2"},
        ],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, sample_a, sample_b)


def test_submit_empty_spreadsheet_is_rejected(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload([]), token=insider_token)

    assert_form_invalid(response, "Spreadsheet must contain at least one row.")
    _assert_unchanged(session, sample_a, sample_b)


# ── Submit: access and CSRF ─────────────────────────────────────────────────


def test_submit_denies_client(
    client: TestClient, session: SyncSession, project_samples, user_token: str,
):
    project, sample_a, sample_b = project_samples

    response = post_form(client, _path(project.id), _payload(
        [_row(sample_a, Tissue="kidney", Batch="b1"), _row(sample_b, Tissue="lung", Batch="b2")],
        extra_columns=["Batch"],
    ), token=user_token)

    assert response.status_code == 403
    _assert_unchanged(session, sample_a, sample_b)


def test_submit_unknown_project_is_404(client: TestClient, insider_token: str):
    response = post_form(client, _path(999999), _payload([]), token=insider_token)
    assert response.status_code == 404


def test_submit_csrf_mismatch_changes_nothing(
    client: TestClient, session: SyncSession, project_samples, insider_token: str,
):
    project, sample_a, sample_b = project_samples

    response = post_form_csrf_mismatch(client, _path(project.id), _payload(
        [_row(sample_a, Tissue="kidney", Batch="b1"), _row(sample_b, Tissue="lung", Batch="b2")],
        extra_columns=["Batch"],
    ), token=insider_token)

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    _assert_unchanged(session, sample_a, sample_b)
