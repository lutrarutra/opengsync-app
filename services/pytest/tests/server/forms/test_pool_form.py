"""PoolForm: create, edit, clone — rendering, permissions, field validation, and persistence.

Pool access is derived from the associated sequencing request.  A pool without a
``seq_request_id`` is only accessible to insiders and admins.
"""

import sqlalchemy as sa

import re

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_pool, create_seq_request
from .._http import (
    assert_flash,
    delete,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

CREATE = "/htmx/pools/create"
EDIT = "/htmx/pools/{pool_id}/edit"
CLONE = "/htmx/pools/{pool_id}/clone"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _edit_path(pool_id: int) -> str:
    return EDIT.format(pool_id=pool_id)


def _clone_path(pool_id: int) -> str:
    return CLONE.format(pool_id=pool_id)


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "name": "Test_Pool_001",
        "pool_type": str(C.PoolType.EXTERNAL.id),
        "status": str(C.PoolStatus.DRAFT.id),
        "contact_name": "Primary Contact",
        "contact_email": "contact@example.com",
        "contact_phone": "+1 555 0100",
        "num_m_reads_requested": "",
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _commit(session: SyncSession) -> None:
    session.commit()


def _pool(session: SyncSession, name: str) -> models.Pool | None:
    """Look up a pool by exact name match."""
    session.expire_all()
    return session.first(sa.select(models.Pool).where(models.Pool.name == name))


def _reload(session: SyncSession, pool: models.Pool) -> models.Pool:
    session.expire_all()
    return session.get_one(Q.pool.select(id=pool.id))


# ── Create ──────────────────────────────────────────────────────────────────


def test_create_form_get_renders_fields(
    client: TestClient,
    user,
    user_token: str,
):
    response = get(client, CREATE, user_token)

    assert response.status_code == 200
    assert 'name="name"' in response.text
    assert 'name="pool_type"' in response.text
    assert 'name="status"' in response.text
    assert 'name="contact_name"' in response.text
    assert 'name="contact_email"' in response.text
    assert 'name="csrf_token"' in response.text


def test_create_form_get_requires_authentication(client: TestClient):
    response = get(client, CREATE)

    assert response.status_code == 303
    assert "/auth/login" in response.headers["location"]


def test_create_persists_with_contact_fields(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    name = "New_Pool_Created"
    response = post_form(
        client,
        CREATE,
        _payload(name=name),
        token=user_token,
    )

    assert_htmx_redirect(response, "/pools/")
    assert_flash(response, "Pool Created!", category="success")

    pool = _pool(session, name)
    assert pool is not None
    assert pool.owner_id == user.id
    assert pool.name == name
    assert pool.type == C.PoolType.EXTERNAL
    assert pool.status == C.PoolStatus.DRAFT
    assert pool.contact.name == "Primary Contact"
    assert pool.contact.email == "contact@example.com"
    assert pool.contact.phone == "+1 555 0100"
    assert pool.num_m_reads_requested is None
    assert pool.seq_request_id is None


def test_create_persists_with_existing_user_as_contact(
    client: TestClient,
    session: SyncSession,
    user,
    user_2,
    user_token: str,
):
    name = "User_Contact_Pool"
    response = post_form(
        client,
        CREATE,
        _payload(name=name, contact=user_2.id),
        token=user_token,
    )

    assert_htmx_redirect(response, "/pools/")

    pool = _pool(session, name)
    assert pool is not None
    assert pool.contact.name == user_2.name
    assert pool.contact.email == user_2.email


def test_create_requires_name(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload(name="x" * 3),  # below min_length=4
        token=user_token,
    )

    assert_form_invalid(response)
    assert _pool(session, "Test_Pool_001") is None


def test_create_name_min_length(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload(name="ab"),  # min_length=4 on the form
        token=user_token,
    )

    assert_form_invalid(response)
    assert "at least 4" in response.text


def test_create_name_max_length(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload(name="x" * (models.Pool.name.type.length + 1)),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "at most 64" in response.text
    assert session.count(Q.pool.select(user_id=user.id)) == 0


def test_create_requires_contact_name_when_no_user_selected(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """contact_name is a required field at the Pydantic level, so the custom
    "Select an existing contact …" handler message is never reached —
    Pydantic validation rejects the empty value first."""
    response = post_form(
        client,
        CREATE,
        _payload(contact_name="", contact_email="contact@example.com"),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "Contact Name is required" in response.text
    assert session.count(Q.pool.select(user_id=user.id)) == 0


def test_create_requires_contact_email_when_no_user_selected(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload(contact_name="Primary Contact", contact_email=""),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "Contact Email is required" in response.text
    assert session.count(Q.pool.select(user_id=user.id)) == 0


def test_create_unknown_contact_user_falls_back_to_manual_contact(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """A non-existent user ID as contact is silently ignored — the form falls
    back to the manual contact_name / contact_email fields."""
    name = "Ghost_Contact_Pool"
    response = post_form(
        client,
        CREATE,
        _payload(name=name, contact=999999),
        token=user_token,
    )

    assert_htmx_redirect(response, "/pools/")
    pool = _pool(session, name)
    assert pool is not None
    assert pool.contact.name == "Primary Contact"
    assert pool.contact.email == "contact@example.com"


def test_create_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    response = post_form_csrf_mismatch(
        client,
        CREATE,
        _payload(),
        token=user_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert session.count(Q.pool.select(user_id=user.id)) == 0


# ── Edit ────────────────────────────────────────────────────────────────────


def test_edit_form_get_renders_pool_values(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    pool.name = "Pool_To_Edit"
    _commit(session)

    response = get(client, _edit_path(pool.id), user_token)

    assert response.status_code == 200
    assert "Pool_To_Edit" in response.text
    assert 'name="name"' in response.text
    assert 'name="csrf_token"' in response.text


def test_edit_form_get_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    response = get(client, _edit_path(pool.id), user_2_token)

    assert response.status_code == 403


def test_edit_form_get_unknown_pool_is_404(
    client: TestClient,
    user_token: str,
):
    assert get(client, _edit_path(999999), user_token).status_code == 404


def test_edit_persists_changes(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    response = post_form(
        client,
        _edit_path(pool.id),
        _payload(
            name="Updated_Pool_Name",
            pool_type=C.PoolType.INTERNAL.id,
            status=C.PoolStatus.STORED.id,
            contact_name="Updated Contact",
            contact_email="updated@example.com",
            contact_phone="+1 555 9999",
            num_m_reads_requested="50.5",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/pools/{pool.id}")
    assert_flash(response, "Changes Saved!", category="success")

    updated = _reload(session, pool)
    assert updated.name == "Updated_Pool_Name"
    assert updated.type == C.PoolType.INTERNAL
    assert updated.status == C.PoolStatus.STORED
    assert updated.contact.name == "Updated Contact"
    assert updated.contact.email == "updated@example.com"
    assert updated.contact.phone == "+1 555 9999"
    assert updated.num_m_reads_requested == 50.5


def test_edit_denied_for_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    response = post_form(
        client,
        _edit_path(pool.id),
        _payload(name="Hijacked_Pool"),
        token=user_2_token,
    )

    assert response.status_code == 403
    assert _reload(session, pool).name != "Hijacked_Pool"


def test_edit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    response = post_form_csrf_mismatch(
        client,
        _edit_path(pool.id),
        _payload(name="CSRF_Pool"),
        token=user_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert _reload(session, pool).name != "CSRF_Pool"


def test_edit_unknown_pool_is_404(
    client: TestClient,
    user_token: str,
):
    response = post_form(
        client,
        _edit_path(999999),
        _payload(name="Ghost_Pool"),
        token=user_token,
    )

    assert response.status_code == 404


# ── Clone ───────────────────────────────────────────────────────────────────


def test_clone_form_get_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    user_token,
    insider_token,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    denied = get(client, _clone_path(pool.id), user_token)
    assert denied.status_code == 403

    allowed = get(client, _clone_path(pool.id), insider_token)
    assert allowed.status_code == 200
    assert pool.name in allowed.text


def test_clone_form_get_unknown_pool_is_404(
    client: TestClient,
    insider_token: str,
):
    assert get(client, _clone_path(999999), insider_token).status_code == 404


def test_clone_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    user_token,
    insider_token,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    denied = post_form(
        client,
        _clone_path(pool.id),
        _payload(name="Cloned_Pool"),
        token=user_token,
    )
    assert denied.status_code == 403


def test_clone_insider_can_clone_pool(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token,
):
    """Clone transfers ownership to the insider performing the clone and copies
    the original pool's contact details, seq_request, and num_m_reads."""
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    pool.type = C.PoolType.INTERNAL
    pool.num_m_reads_requested = 100.0
    pool.contact.name = "Clone Source"
    pool.contact.email = "source@example.com"
    pool.contact.phone = "+1 555 7777"
    _commit(session)

    clone_name = "Cloned_Pool_001"
    response = post_form(
        client,
        _clone_path(pool.id),
        _payload(
            name=clone_name,
            pool_type=C.PoolType.INTERNAL.id,
            status=C.PoolStatus.STORED.id,
            contact_name="Cloned Contact",
            contact_email="clone@example.com",
            num_m_reads_requested="100.0",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, "/pools/")
    assert_flash(response, "Pool Cloned!", category="success")

    cloned = _pool(session, clone_name)
    assert cloned is not None
    assert cloned.owner_id == insider.id  # clone is owned by the cloner
    assert cloned.type == C.PoolType.INTERNAL
    assert cloned.status == C.PoolStatus.STORED
    assert cloned.num_m_reads_requested == 100.0
    assert cloned.seq_request_id == pool.seq_request_id
    assert cloned.contact.name == "Clone Source"
    assert cloned.contact.email == "source@example.com"
    assert cloned.contact.phone == "+1 555 7777"


def test_cloned_pool_page_links_original_pool(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    pool.name = "Clone_Origin_Pool"
    _commit(session)

    response = post_form(
        client,
        _clone_path(pool.id),
        _payload(name="Clone_Of_Origin", pool_type=pool.type.id),
        token=insider_token,
    )
    assert_htmx_redirect(response, "/pools/")

    cloned = _pool(session, "Clone_Of_Origin")
    assert cloned is not None
    assert cloned.original_pool_id == pool.id

    cloned_page = get(client, f"/pools/{cloned.id}", insider_token)
    assert cloned_page.status_code == 200
    assert "Original Pool" in cloned_page.text
    assert "Clone_Origin_Pool" in cloned_page.text
    assert f"/pools/{pool.id}?from=pool%40{cloned.id}" in cloned_page.text

    original_page = get(client, f"/pools/{pool.id}", insider_token)
    assert original_page.status_code == 200
    assert "Original Pool" not in original_page.text


def test_clone_rejects_changed_pool_type(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    pool.type = C.PoolType.INTERNAL
    _commit(session)

    response = post_form(
        client,
        _clone_path(pool.id),
        _payload(
            name="Changed_Type_Pool",
            pool_type=C.PoolType.EXTERNAL.id,
        ),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "Pool type cannot be changed" in response.text
    assert _pool(session, "Changed_Type_Pool") is None


def test_clone_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token,
):
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    _commit(session)

    response = post_form_csrf_mismatch(
        client,
        _clone_path(pool.id),
        _payload(name="CSRF_Clone"),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert _pool(session, "CSRF_Clone") is None

def test_edit_client_cannot_change_status(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    pool = create_pool(session, user, create_seq_request(session, user))
    _commit(session)

    response = post_form(client, _edit_path(pool.id), _payload(status=C.PoolStatus.STORED.id), token=user_token)

    assert_form_invalid(response, "Only insiders can change pool status.")
    assert _reload(session, pool).status == C.PoolStatus.DRAFT


def test_create_client_cannot_choose_status(
    client: TestClient,
    session: SyncSession,
    user_token: str,
):
    response = post_form(client, "/htmx/pools/create", _payload(name="Stored_Pool", status=C.PoolStatus.STORED.id), token=user_token)

    assert_form_invalid(response, "You can only create a pool with status DRAFT.")
    session.expire_all()
    assert session.first(Q.pool.select().where(models.Pool.name == "Stored_Pool")) is None


def test_status_is_read_only_for_client(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
    insider_token: str,
):
    pool = create_pool(session, user, create_seq_request(session, user))
    _commit(session)

    for path in (_edit_path(pool.id), "/htmx/pools/create"):
        assert re.search(r'<select[^>]*\bdisabled\b[^>]*name="status"', get(client, path, user_token).text), path
        assert not re.search(r'<select[^>]*\bdisabled\b[^>]*name="status"', get(client, path, insider_token).text), path
    # The read-only select still submits DRAFT (id 0) through its hidden input.
    assert '<input type="hidden" name="status" value="0">' in get(client, "/htmx/pools/create", user_token).text


# ── Clone: library copies, numbering, status (as legacy PoolForm.__clone_pool) ──


def _clone_payload(pool: models.Pool, name: str, status: C.PoolStatus = C.PoolStatus.STORED) -> dict[str, str]:
    return _payload(name=name, pool_type=pool.type.id, status=status.id, num_m_reads_requested="10")


def _pool_with_library(session: SyncSession, user) -> tuple[models.Pool, models.Library, models.Sample]:
    from opengsync_db import actions
    from ...db.create_units import create_library, create_project, create_sample

    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    sample = create_sample(session, user, create_project(session, user))
    library = create_library(session, user, seq_request)
    library.pool_id = pool.id
    session.save(library, flush=True)
    actions.link_sample_library(session, sample_id=sample.id, library_id=library.id)
    actions.add_index_to_library(
        session, library_id=library.id, index_kit_i7_id=None, name_i7="i7", sequence_i7="ACGTACGT",
        index_kit_i5_id=None, name_i5="i5", sequence_i5="TTGGCCAA", orientation=None,
    )
    actions.dilute_pool(session, pool, qubit_concentration=1.5, operator_id=user.id)
    _commit(session)
    return pool, library, sample


def test_clone_copies_libraries_with_samples_and_indices(client: TestClient, session: SyncSession, user, insider_token):
    pool, library, sample = _pool_with_library(session, user)

    response = post_form(client, _clone_path(pool.id), _clone_payload(pool, "Cloned_With_Libs"), token=insider_token)

    assert_htmx_redirect(response, "/pools/")
    cloned = _pool(session, "Cloned_With_Libs")
    [cloned_library] = cloned.libraries
    assert cloned_library.id != library.id
    assert cloned_library.original_library_id == library.id
    assert cloned_library.clone_number == library.clone_number + 1
    assert cloned_library.status == C.LibraryStatus.POOLED
    assert [link.sample_id for link in cloned_library.sample_links] == [sample.id]
    assert [(i.sequence_i7, i.sequence_i5) for i in cloned_library.indices] == [("ACGTACGT", "TTGGCCAA")]
    assert [(d.identifier, d.qubit_concentration) for d in cloned.dilutions] == [("A", 1.5)]
    assert [lib.id for lib in _reload(session, pool).libraries] == [library.id]  # original untouched


def test_clone_number_counts_the_originals_clones(client: TestClient, session: SyncSession, user, insider_token):
    pool, _, _ = _pool_with_library(session, user)

    post_form(client, _clone_path(pool.id), _clone_payload(pool, "Clone_One"), token=insider_token)
    first = _pool(session, "Clone_One")
    post_form(client, _clone_path(first.id), _clone_payload(pool, "Clone_Two"), token=insider_token)

    second = _pool(session, "Clone_Two")
    assert (first.clone_number, first.original_pool_id) == (1, pool.id)
    assert (second.clone_number, second.original_pool_id) == (2, pool.id)  # a clone of a clone points to the original


def test_clone_keeps_the_chosen_status(client: TestClient, session: SyncSession, user, insider_token):
    pool, _, _ = _pool_with_library(session, user)

    response = post_form(client, _clone_path(pool.id), _clone_payload(pool, "Clone_Draft", C.PoolStatus.DRAFT), token=insider_token)

    assert_htmx_redirect(response, "/pools/")
    assert _pool(session, "Clone_Draft").status == C.PoolStatus.DRAFT


def test_clone_form_prefills_stored_status(client: TestClient, session: SyncSession, user, insider_token):
    pool, _, _ = _pool_with_library(session, user)

    response = get(client, _clone_path(pool.id), insider_token)

    assert response.status_code == 200
    assert re.search(rf'<option value="{C.PoolStatus.STORED.id}"\s+selected', response.text)


# ── Clone: shared BA report ─────────────────────────────────────────────────
# The clone points to the same BA report media file as the original (as legacy); it is not copied.


def _ba_report(session: SyncSession, user) -> models.MediaFile:
    import uuid as uuid_
    return session.save(Q.media_file.create(
        name="ba-report", extension=".pdf", size_bytes=1, type=C.MediaFileType.BIOANALYZER_REPORT,
        uploader_id=user.id, uuid=str(uuid_.uuid4()),
    ), flush=True)


def _pool_with_ba_report(session: SyncSession, user, insider) -> tuple[models.Pool, models.MediaFile]:
    """A pool without libraries (so it can be deleted), measured with a BA report."""
    pool = create_pool(session, user, create_seq_request(session, user))
    report = _ba_report(session, insider)
    pool.ba_report_id, pool.avg_fragment_size = report.id, 400
    session.save(pool, flush=True)
    _commit(session)
    return pool, report


def _clone(client: TestClient, session: SyncSession, pool: models.Pool, insider_token: str, name: str) -> models.Pool:
    assert_htmx_redirect(post_form(client, _clone_path(pool.id), _clone_payload(pool, name), token=insider_token), "/pools/")
    clone = _pool(session, name)
    assert clone is not None
    return clone


def test_clone_shares_the_ba_report(client: TestClient, session: SyncSession, user, insider, insider_token):
    pool, report = _pool_with_ba_report(session, user, insider)

    clone = _clone(client, session, pool, insider_token, "Clone_BA")

    assert (clone.ba_report_id, clone.avg_fragment_size) == (report.id, 400)


def test_deleting_the_original_keeps_the_clones_ba_report(client: TestClient, session: SyncSession, user, insider, insider_token):
    pool, report = _pool_with_ba_report(session, user, insider)
    clone = _clone(client, session, pool, insider_token, "Clone_After_Delete")
    pool_id, report_id = pool.id, report.id

    response = delete(client, f"/htmx/pools/{pool_id}/delete", insider_token)

    assert response.status_code == 204, response.text
    session.expire_all()
    assert session.first(Q.pool.select(id=pool_id)) is None
    assert session.first(Q.media_file.select(id=report_id)) is not None  # the report is not deleted with the pool
    assert (_reload(session, clone).ba_report_id, _reload(session, clone).avg_fragment_size) == (report_id, 400)


def test_new_ba_report_on_the_original_leaves_the_clone_on_the_old_one(client: TestClient, session: SyncSession, user, insider, insider_token):
    """A new BA report run creates a new media file and re-points only the measured objects
    (``CompleteBAReport``); the old file is kept."""
    pool, old_report = _pool_with_ba_report(session, user, insider)
    clone = _clone(client, session, pool, insider_token, "Clone_Old_Report")

    new_report = _ba_report(session, insider)
    pool = _reload(session, pool)
    pool.ba_report_id, pool.avg_fragment_size = new_report.id, 500
    session.save(pool, flush=True)
    _commit(session)

    assert (_reload(session, pool).ba_report_id, _reload(session, pool).avg_fragment_size) == (new_report.id, 500)
    assert (_reload(session, clone).ba_report_id, _reload(session, clone).avg_fragment_size) == (old_report.id, 400)
    assert session.first(Q.media_file.select(id=old_report.id)) is not None


def test_deleting_the_ba_report_clears_it_on_original_and_clone(client: TestClient, session: SyncSession, user, insider, insider_token):
    pool, report = _pool_with_ba_report(session, user, insider)
    clone = _clone(client, session, pool, insider_token, "Clone_Report_Deleted")
    report_id = report.id

    response = delete(client, f"/htmx/files/{report_id}/delete", insider_token)

    assert response.status_code == 204, response.text
    session.expire_all()
    assert session.first(Q.media_file.select(id=report_id)) is None
    for p in (pool, clone):  # ondelete="SET NULL"; the fragment size stays
        assert (_reload(session, p).ba_report_id, _reload(session, p).avg_fragment_size) == (None, 400)
