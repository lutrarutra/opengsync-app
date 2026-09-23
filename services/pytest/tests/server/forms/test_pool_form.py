"""PoolForm: create, edit, clone — rendering, permissions, field validation, and persistence.

Pool access is derived from the associated sequencing request.  A pool without a
``seq_request_id`` is only accessible to insiders and admins.
"""

import sqlalchemy as sa

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_pool, create_seq_request
from .._http import (
    assert_flash,
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
    user_token: str,
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
        token=user_token,
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