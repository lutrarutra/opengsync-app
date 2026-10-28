"""EditLibraryPropertiesAction: library properties as a spreadsheet (one column per property).

Context is a sequencing request, a project or a single library (query parameter). As
legacy ``LibraryPropertyForm`` / ``LibraryPropertiesForm``: viewing needs READ on the
context; the table has a row per library and a column per property key; submitting sets
every property column for every row (empty cells → ``None``), removes deleted columns and
redirects back to the context page. Rows can only name libraries of the context.

Editing needs WRITE on every library of the context (``Q.library.access_level``: insiders
always, other users only while the library's request is a draft); otherwise the table is
read-only and saving is 403. Legacy: non-insiders only for DRAFT libraries in library
context, and only insiders in project/request context.

The library is one read-only ``DBObjectColumn`` ("name [id]") whose options are the libraries
of the context, so a row naming any other library fails validation.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_library, create_project, create_sample, create_seq_request
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch, spreadsheet_payload


def _path(client: TestClient, route: str = "Begin") -> str:
    return client.app.url_path_for(f"EditLibraryPropertiesAction.{route}")  # type: ignore[attr-defined]


def _cell(library: models.Library) -> str:
    return f"{library.name} [{library.id}]"


def _payload(properties: list[str], rows: list[tuple[models.Library | str, list[Any]]]) -> dict[str, str]:
    """Columns: Library ("name [id]", or the raw cell when a string), then one per property (display name = key)."""
    return spreadsheet_payload(
        ["Library", *properties],
        [[library if isinstance(library, str) else _cell(library), *values] for library, values in rows],
    )


def _properties(session: SyncSession, library: models.Library) -> dict | None:
    session.expire_all()
    return session.get_one(Q.library.select(id=library.id)).properties


class Request:
    """A request owned by ``user`` with two libraries, A (tissue=liver) and B (tissue=lung, donor=D1)."""

    def __init__(self, session: SyncSession, user: models.User):
        self.seq_request = create_seq_request(session, user)
        self.a = create_library(session, user, self.seq_request)
        self.b = create_library(session, user, self.seq_request)
        self.a.properties = {"tissue": "liver"}
        self.b.properties = {"tissue": "lung", "donor": "D1"}
        session.save(self.a, flush=True)
        session.save(self.b, flush=True)
        session.commit()

    @property
    def params(self) -> dict[str, int]:
        return {"seq_request_id": self.seq_request.id}


@pytest.fixture
def req(session: SyncSession, user) -> Request:
    return Request(session, user)


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_request_context(client: TestClient, req: Request, user_token: str):
    response = get(client, _path(client), user_token, params=req.params)

    assert response.status_code == 200, response.text
    for text in (_cell(req.a), _cell(req.b), "liver", "lung", "D1", "Tissue", "Donor"):
        assert text in response.text
    assert "Library Name" not in response.text


def test_render_project_context(client: TestClient, session: SyncSession, user, user_token: str):
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    library.properties = {"organism": "mouse"}
    session.save(library, flush=True)
    sample = create_sample(session, user, project)
    session.add(models.links.SampleLibraryLink(sample_id=sample.id, library_id=library.id))
    outside = create_library(session, user, seq_request)
    session.commit()

    response = get(client, _path(client), user_token, params={"project_id": project.id})

    assert response.status_code == 200, response.text
    assert library.name in response.text and "mouse" in response.text
    assert outside.name not in response.text


def test_render_library_context(client: TestClient, req: Request, user_token: str):
    response = get(client, _path(client), user_token, params={"library_id": req.a.id})

    assert response.status_code == 200, response.text
    assert req.a.name in response.text
    assert req.b.name not in response.text


def test_render_does_not_change_properties(client: TestClient, session: SyncSession, req: Request, user_token: str):
    get(client, _path(client), user_token, params=req.params)
    assert _properties(session, req.b) == {"tissue": "lung", "donor": "D1"}


# ── Access ──────────────────────────────────────────────────────────────────


def test_no_context_is_400(client: TestClient, user_token: str):
    assert get(client, _path(client), user_token).status_code == 400


def test_other_users_request_is_denied(client: TestClient, session: SyncSession, req: Request, user_2_token: str):
    assert get(client, _path(client), user_2_token, params=req.params).status_code == 403
    response = post_form(client, _path(client, "Submit"), _payload(["tissue"], [(req.a, ["brain"])]), token=user_2_token, params=req.params)
    assert response.status_code == 403
    assert _properties(session, req.a) == {"tissue": "liver"}


def test_other_users_library_is_denied(client: TestClient, req: Request, user_2_token: str):
    assert get(client, _path(client), user_2_token, params={"library_id": req.a.id}).status_code == 403


def test_anonymous_is_redirected_to_login(client: TestClient, req: Request):
    for response in (get(client, _path(client), params=req.params), post_form(client, _path(client, "Submit"), {}, params=req.params)):
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")


@pytest.mark.parametrize("param", ["seq_request_id", "project_id", "library_id"])
def test_unknown_context_is_404(client: TestClient, insider_token: str, param: str):
    assert get(client, _path(client), insider_token, params={param: 999999}).status_code == 404


def test_csrf_mismatch_changes_nothing(client: TestClient, session: SyncSession, req: Request, user_token: str):
    response = post_form_csrf_mismatch(
        client, _path(client, "Submit"), _payload(["tissue"], [(req.a, ["brain"]), (req.b, ["lung"])]),
        token=user_token, params=req.params,
    )
    assert response.status_code != 204
    assert _properties(session, req.a) == {"tissue": "liver"}


def test_library_outside_context_cannot_be_edited(
    client: TestClient, session: SyncSession, req: Request, user, user_token: str,
):
    """Rows come from the client: a library of another request (even the user's own) is no option of the column."""
    other = create_library(session, user, create_seq_request(session, user))
    other.properties = {"tissue": "heart"}
    session.save(other, flush=True)
    session.commit()

    response = post_form(client, _path(client, "Submit"), _payload(["tissue"], [(other, ["brain"])]), token=user_token, params=req.params)

    assert_form_invalid(response, f"Invalid value '{_cell(other)}'")
    assert _properties(session, other) == {"tissue": "heart"}


def test_library_context_cannot_edit_other_library(client: TestClient, session: SyncSession, req: Request, user_token: str):
    response = post_form(
        client, _path(client, "Submit"), _payload(["tissue"], [(req.b, ["brain"])]),
        token=user_token, params={"library_id": req.a.id},
    )

    assert_form_invalid(response, f"Invalid value '{_cell(req.b)}'")
    assert _properties(session, req.b) == {"tissue": "lung", "donor": "D1"}


def _submit(session: SyncSession, seq_request: models.SeqRequest) -> None:
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.save(seq_request, flush=True)
    session.commit()


def test_client_cannot_edit_library_of_submitted_request(client: TestClient, session: SyncSession, req: Request, user_token: str):
    _submit(session, req.seq_request)

    assert get(client, _path(client), user_token, params={"library_id": req.a.id}).status_code == 200
    response = post_form(
        client, _path(client, "Submit"), _payload(["tissue"], [(req.a, ["brain"])]),
        token=user_token, params={"library_id": req.a.id},
    )

    assert response.status_code == 403
    assert _properties(session, req.a) == {"tissue": "liver"}


def test_insider_can_edit_library_of_submitted_request(client: TestClient, session: SyncSession, req: Request, insider_token: str):
    _submit(session, req.seq_request)

    response = post_form(
        client, _path(client, "Submit"), _payload(["tissue"], [(req.a, ["brain"])]),
        token=insider_token, params={"library_id": req.a.id},
    )

    assert_htmx_redirect(response, f"/libraries/{req.a.id}")
    assert _properties(session, req.a) == {"tissue": "brain"}


def test_client_cannot_edit_submitted_request(client: TestClient, session: SyncSession, req: Request, user_token: str):
    _submit(session, req.seq_request)

    assert get(client, _path(client), user_token, params=req.params).status_code == 200
    response = post_form(client, _path(client, "Submit"), _payload(["tissue", "donor"], [
        (req.a, ["brain", ""]), (req.b, ["lung", "D1"]),
    ]), token=user_token, params=req.params)

    assert response.status_code == 403
    assert _properties(session, req.a) == {"tissue": "liver"}


def test_insider_can_edit_submitted_request(client: TestClient, session: SyncSession, req: Request, insider_token: str):
    _submit(session, req.seq_request)

    response = post_form(client, _path(client, "Submit"), _payload(["tissue", "donor"], [
        (req.a, ["brain", ""]), (req.b, ["lung", "D1"]),
    ]), token=insider_token, params=req.params)

    assert_htmx_redirect(response, f"/seq_requests/{req.seq_request.id}")
    assert _properties(session, req.a) == {"tissue": "brain", "donor": None}


def test_client_cannot_edit_project_with_a_submitted_request(client: TestClient, session: SyncSession, user, user_token: str):
    """One library without WRITE (its request is submitted) makes the whole project table read-only."""
    project = create_project(session, user)
    draft = create_library(session, user, create_seq_request(session, user))
    submitted_request = create_seq_request(session, user)
    submitted = create_library(session, user, submitted_request)
    for library in (draft, submitted):
        sample = create_sample(session, user, project)
        session.add(models.links.SampleLibraryLink(sample_id=sample.id, library_id=library.id))
    _submit(session, submitted_request)

    response = post_form(client, _path(client, "Submit"), _payload(["organism"], [
        (draft, ["mouse"]), (submitted, ["mouse"]),
    ]), token=user_token, params={"project_id": project.id})

    assert response.status_code == 403
    assert _properties(session, draft) is None


# ── Submit: persistence ─────────────────────────────────────────────────────


def test_edit_values_in_request_context(client: TestClient, session: SyncSession, req: Request, user_token: str):
    response = post_form(client, _path(client, "Submit"), _payload(["tissue", "donor"], [
        (req.a, ["brain", "D2"]), (req.b, [" lung ", "D1"]),
    ]), token=user_token, params=req.params)

    assert_htmx_redirect(response, f"/seq_requests/{req.seq_request.id}")
    assert "tab=request-libraries-tab" in response.headers["HX-Redirect"]
    assert_flash(response, "Changes Saved!", category="success")
    assert _properties(session, req.a) == {"tissue": "brain", "donor": "D2"}
    assert _properties(session, req.b) == {"tissue": "lung", "donor": "D1"}


def test_empty_cell_sets_property_to_none(client: TestClient, session: SyncSession, req: Request, user_token: str):
    response = post_form(client, _path(client, "Submit"), _payload(["tissue", "donor"], [
        (req.a, ["liver", ""]), (req.b, ["lung", ""]),
    ]), token=user_token, params=req.params)

    assert_htmx_redirect(response, f"/seq_requests/{req.seq_request.id}")
    assert _properties(session, req.a) == {"tissue": "liver", "donor": None}
    assert _properties(session, req.b) == {"tissue": "lung", "donor": None}


def test_new_column_adds_property(client: TestClient, session: SyncSession, req: Request, user_token: str):
    response = post_form(client, _path(client, "Submit"), _payload(["tissue", "donor", "batch"], [
        (req.a, ["liver", "", "B1"]), (req.b, ["lung", "D1", "B2"]),
    ]), token=user_token, params=req.params)

    assert_htmx_redirect(response, f"/seq_requests/{req.seq_request.id}")
    assert _properties(session, req.a) == {"tissue": "liver", "donor": None, "batch": "B1"}
    assert _properties(session, req.b) == {"tissue": "lung", "donor": "D1", "batch": "B2"}


def test_deleted_column_removes_property(client: TestClient, session: SyncSession, req: Request, user_token: str):
    response = post_form(client, _path(client, "Submit"), _payload(["tissue"], [
        (req.a, ["liver"]), (req.b, ["lung"]),
    ]), token=user_token, params=req.params)

    assert_htmx_redirect(response, f"/seq_requests/{req.seq_request.id}")
    assert _properties(session, req.a) == {"tissue": "liver"}
    assert _properties(session, req.b) == {"tissue": "lung"}


def test_edit_in_project_context_redirects_to_project(client: TestClient, session: SyncSession, user, user_token: str):
    project = create_project(session, user)
    library = create_library(session, user, create_seq_request(session, user))
    sample = create_sample(session, user, project)
    session.add(models.links.SampleLibraryLink(sample_id=sample.id, library_id=library.id))
    session.commit()

    response = post_form(client, _path(client, "Submit"), _payload(["organism"], [(library, ["mouse"])]), token=user_token, params={"project_id": project.id})

    assert_htmx_redirect(response, f"/projects/{project.id}")
    assert "tab=libraries-tab" in response.headers["HX-Redirect"]
    assert _properties(session, library) == {"organism": "mouse"}


def test_edit_in_library_context_redirects_to_library(client: TestClient, session: SyncSession, req: Request, user_token: str):
    response = post_form(client, _path(client, "Submit"), _payload(["tissue"], [(req.a, ["brain"])]), token=user_token, params={"library_id": req.a.id})

    assert_htmx_redirect(response, f"/libraries/{req.a.id}")
    assert _properties(session, req.a) == {"tissue": "brain"}
    assert _properties(session, req.b) == {"tissue": "lung", "donor": "D1"}


def test_library_without_properties(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()

    assert get(client, _path(client), user_token, params={"seq_request_id": seq_request.id}).status_code == 200
    response = post_form(client, _path(client, "Submit"), _payload(["tissue"], [(library, ["skin"])]), token=user_token, params={"seq_request_id": seq_request.id})

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert _properties(session, library) == {"tissue": "skin"}


# ── Submit: validation ──────────────────────────────────────────────────────


def test_too_long_value_is_rejected(client: TestClient, session: SyncSession, req: Request, user_token: str):
    response = post_form(client, _path(client, "Submit"), _payload(["tissue"], [
        (req.a, ["x" * 1001]), (req.b, ["lung"]),
    ]), token=user_token, params=req.params)

    assert_form_invalid(response)
    assert _properties(session, req.a) == {"tissue": "liver"}


def test_library_id_and_name_mismatch_is_rejected(client: TestClient, session: SyncSession, req: Request, user_token: str):
    """The cell must be an option verbatim: another library's id under this name is not accepted."""
    response = post_form(client, _path(client, "Submit"), _payload(["tissue"], [
        (f"{req.a.name} [{req.b.id}]", ["brain"]),
    ]), token=user_token, params=req.params)

    assert_form_invalid(response)
    assert _properties(session, req.b) == {"tissue": "lung", "donor": "D1"}


def test_duplicate_library_is_rejected(client: TestClient, session: SyncSession, req: Request, user_token: str):
    response = post_form(client, _path(client, "Submit"), _payload(["tissue"], [
        (req.a, ["brain"]), (req.a, ["heart"]),
    ]), token=user_token, params=req.params)

    assert_form_invalid(response, "is not unique")
    assert _properties(session, req.a) == {"tissue": "liver"}


def test_missing_library_is_rejected(client: TestClient, session: SyncSession, req: Request, user_token: str):
    response = post_form(client, _path(client, "Submit"), _payload(["tissue"], [
        ("", ["brain"]), (req.b, ["lung"]),
    ]), token=user_token, params=req.params)

    assert_form_invalid(response, "Missing value for 'Library'")
    assert _properties(session, req.a) == {"tissue": "liver"}


def test_plain_library_name_resolves_to_library(client: TestClient, session: SyncSession, req: Request, user_token: str):
    """A pasted name without "[id]" stands for the one library of the context with that name."""
    response = post_form(client, _path(client, "Submit"), _payload(["tissue"], [
        (req.a.name, ["brain"]),
    ]), token=user_token, params=req.params)

    assert_htmx_redirect(response, f"/seq_requests/{req.seq_request.id}")
    assert _properties(session, req.a) == {"tissue": "brain"}
