"""LibraryForm: edit rendering, field persistence, name rules, and access control.

Access is derived from the library's sequencing request: WRITE requires a DRAFT
request owned by (or shared with) the viewer, matching the legacy Flask route.
"""

import uuid

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_group, create_library, create_seq_request
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

EDIT = "/htmx/libraries/{library_id}/edit"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _edit_path(library_id: int) -> str:
    return EDIT.format(library_id=library_id)


def _payload(name: str, **overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "name": name,
        "library_type": str(C.LibraryType.BULK_RNA_SEQ.id),
        "genome": str(C.GenomeRef.CUSTOM.id),
        "status": str(C.LibraryStatus.DRAFT.id),
        "nuclei_isolation": "on",
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _library_for(session: SyncSession, user: models.User) -> models.Library:
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()
    return library


def _reload(session: SyncSession, library: models.Library) -> models.Library:
    session.expire_all()
    return session.get_one(Q.library.select(id=library.id))


def _expected_name(sample_name: str, library_type: C.LibraryType) -> str:
    return f"{sample_name}_{library_type.identifier}"


def test_library_form_exposes_only_edit_routes():
    from server.forms.models.LibraryForm import LibraryForm

    assert {(route.method, route.name) for route in LibraryForm._routes} == {
        ("GET", "LibraryForm.Edit"),
        ("POST", "LibraryForm.Edit"),
    }


def test_edit_form_get_renders_library(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)

    response = get(client, _edit_path(library.id), user_token)

    assert response.status_code == 200
    assert library.sample_name in response.text
    assert 'name="name"' in response.text
    assert 'name="library_type"' in response.text
    assert 'name="genome"' in response.text
    assert 'name="status"' in response.text
    assert 'name="mux_type"' in response.text
    assert 'name="csrf_token"' in response.text
    assert "None" in response.text


def test_edit_form_get_unknown_library_is_404(client: TestClient, user_token: str):
    assert get(client, _edit_path(999999), user_token).status_code == 404


def test_edit_form_get_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    library = _library_for(session, user)

    assert get(client, _edit_path(library.id), user_2_token).status_code == 403


def test_edit_form_get_denied_for_submitted_seq_request(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)
    library.seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.commit()

    assert get(client, _edit_path(library.id), user_token).status_code == 403


def test_edit_persists_fields_and_derives_name(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)

    response = post_form(
        client,
        _edit_path(library.id),
        _payload(
            "Renamed_Library",
            library_type=C.LibraryType.TENX_SC_ATAC.id,
            genome=C.GenomeRef.MOUSE.id,
            status=C.LibraryStatus.PREPARING.id,
        ),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert_flash(
        response,
        f"Updated library '{_expected_name('Renamed_Library', C.LibraryType.TENX_SC_ATAC)}'",
        category="success",
    )

    updated = _reload(session, library)
    assert updated.sample_name == "Renamed_Library"
    assert updated.name == _expected_name("Renamed_Library", C.LibraryType.TENX_SC_ATAC)
    assert updated.type == C.LibraryType.TENX_SC_ATAC
    assert updated.genome_ref == C.GenomeRef.MOUSE
    assert updated.status == C.LibraryStatus.PREPARING


def test_edit_nuclei_isolation_toggle(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)
    library.nuclei_isolation = True
    session.commit()

    # Unchecked checkboxes are omitted from a browser POST entirely.
    payload = _payload("No_Nuclei")
    del payload["nuclei_isolation"]

    response = post_form(
        client,
        _edit_path(library.id),
        payload,
        token=user_token,
    )

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert _reload(session, library).nuclei_isolation is False


def test_edit_mux_type_none_selection(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)
    library.mux_type = C.MUXType.TENX_FLEX_PROBE
    session.commit()

    for empty_value in ("", "-1"):
        response = post_form(
            client,
            _edit_path(library.id),
            _payload("Unmuxed_Library", mux_type=empty_value),
            token=user_token,
        )
        assert_htmx_redirect(response, f"/libraries/{library.id}")
        assert _reload(session, library).mux_type is None


def test_edit_mux_type_custom_persists(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)
    assert C.MUXType.CUSTOM.id == 0

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("Custom_Mux_Library", mux_type=C.MUXType.CUSTOM.id),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert _reload(session, library).mux_type == C.MUXType.CUSTOM


def test_edit_mux_type_value_persists(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("Flex_Mux_Library", mux_type=C.MUXType.TENX_FLEX_PROBE.id),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert _reload(session, library).mux_type == C.MUXType.TENX_FLEX_PROBE


def test_edit_preserves_index_type(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)
    library.index_type = C.IndexType.SINGLE_INDEX_I7
    session.commit()

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("Indexed_Library"),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert _reload(session, library).index_type == C.IndexType.SINGLE_INDEX_I7


def test_edit_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    library = _library_for(session, user)

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("Stolen_Library"),
        token=user_2_token,
    )

    assert response.status_code == 403
    assert _reload(session, library).sample_name == library.sample_name


def test_edit_denied_for_submitted_seq_request(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)
    library.seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.commit()

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("Locked_Library"),
        token=user_token,
    )

    assert response.status_code == 403
    assert _reload(session, library).sample_name == library.sample_name


def test_edit_insider_can_rename(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    library = _library_for(session, user)

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("Insider_Library"),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert _reload(session, library).sample_name == "Insider_Library"


def test_edit_allowed_for_seq_request_group_member(
    client: TestClient,
    session: SyncSession,
    user,
    user_2,
    user_2_token: str,
):
    seq_request = create_seq_request(session, user)
    group = create_group(session)
    seq_request.group_id = group.id
    session.save(
        Q.affiliation.create(user=user_2, group=group, type=C.AffiliationType.MEMBER),
        flush=True,
    )
    library = create_library(session, user, seq_request)
    session.commit()

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("Group_Library"),
        token=user_2_token,
    )

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert _reload(session, library).sample_name == "Group_Library"


def test_edit_invalid_characters_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("Invalid Library!"),
        token=user_token,
    )

    assert_form_invalid(response, "Invalid character in name")
    assert _reload(session, library).sample_name == library.sample_name


def test_edit_requires_name(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)

    response = post_form(client, _edit_path(library.id), {}, token=user_token)

    assert_form_invalid(response)
    assert "Name is required" in response.text
    assert _reload(session, library).sample_name == library.sample_name


def test_edit_name_min_length(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("ab"),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "at least 3" in response.text
    assert _reload(session, library).sample_name == library.sample_name


def test_edit_name_max_length(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("x" * (models.Library.sample_name.type.length + 1)),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "at most 64" in response.text
    assert _reload(session, library).sample_name == library.sample_name


def test_edit_invalid_library_type_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)

    response = post_form(
        client,
        _edit_path(library.id),
        _payload("Bad_Type_Library", library_type="not-a-number"),
        token=user_token,
    )

    assert_form_invalid(response)
    assert _reload(session, library).sample_name == library.sample_name


def test_edit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    library = _library_for(session, user)

    response = post_form_csrf_mismatch(
        client,
        _edit_path(library.id),
        _payload("CSRF_Library", **{}),
        token=user_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert _reload(session, library).sample_name == library.sample_name


def test_edit_name_collision_across_libraries_is_allowed(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """Libraries may share a sample name; the derived name includes the type identifier."""
    seq_request = create_seq_request(session, user)
    first = create_library(session, user, seq_request)
    second = create_library(session, user, seq_request)
    first.sample_name = f"Shared_{uuid.uuid4().hex[:6]}"
    second.sample_name = f"Other_{uuid.uuid4().hex[:6]}"
    session.commit()

    response = post_form(
        client,
        _edit_path(second.id),
        _payload(first.sample_name),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/libraries/{second.id}")
    assert _reload(session, second).sample_name == first.sample_name