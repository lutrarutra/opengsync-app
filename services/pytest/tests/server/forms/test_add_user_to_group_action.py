"""AddUserToGroupAction: render, permissions, validation, and adding users.

Access control:
- **Init()** requires the group to exist (404 if not).
- **GET (Begin)** requires WRITE on the group (via group_permissions).
- **POST (Submit)** requires WRITE on the group.
- Validates user exists by email, is not OWNER affiliation, and not already in group.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_group, create_user
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

PREFIX = "/htmx/groups"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _render_path(group_id: int) -> str:
    return f"{PREFIX}/{group_id}/add-user"


def _submit_path(group_id: int) -> str:
    return f"{PREFIX}/{group_id}/add-user"


def _payload(**overrides: object) -> dict[str, str]:
    """Default payload adds user as MEMBER (id=3)."""
    data: dict[str, str] = {
        "email": "",
        "affiliation_type": "3",
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _commit(session: SyncSession) -> None:
    session.commit()


def _group_with_owner(session: SyncSession, user: models.User) -> models.Group:
    """Create a group and make *user* the OWNER so they have WRITE permission."""
    group = create_group(session)
    group.user_links.append(
        Q.affiliation.create(user=user, group=group, type=C.AffiliationType.OWNER)
    )
    session.save(group)
    _commit(session)
    return group


def _create_extra_user(session: SyncSession, email: str = "tester@example.com") -> models.User:
    """Create a plain CLIENT user for adding to groups and commit."""
    user = session.save(Q.user.create(
        email=email,
        hashed_password="x",
        first_name="Test",
        last_name="Tester",
        role=C.UserRole.CLIENT,
    ), flush=True)
    _commit(session)
    return user


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_get_allows_owner(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """Group owner (OWNER affiliation) has WRITE access."""
    group = _group_with_owner(session, user)

    response = get(client, _render_path(group.id), user_token)

    assert response.status_code == 200
    assert 'name="email"' in response.text
    assert 'name="affiliation_type"' in response.text
    assert 'name="csrf_token"' in response.text


def test_render_get_denies_stranger(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    """A user with no affiliation lacks WRITE."""
    group = _group_with_owner(session, user)

    response = get(client, _render_path(group.id), user_2_token)

    assert response.status_code == 403


def test_render_get_unknown_is_404(
    client: TestClient,
    user_token: str,
):
    assert get(client, _render_path(999999), user_token).status_code == 404


# ── Submit (POST) ────────────────────────────────────────────────────────────


def test_submit_requires_write(
    client: TestClient,
    session: SyncSession,
    user,
    user_2_token: str,
):
    group = _group_with_owner(session, user)
    target = _create_extra_user(session)

    response = post_form(
        client,
        _submit_path(group.id),
        _payload(email=target.email),
        token=user_2_token,
    )

    assert response.status_code == 403


def test_submit_adds_user_as_member(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    group = _group_with_owner(session, user)
    target = _create_extra_user(session)

    response = post_form(
        client,
        _submit_path(group.id),
        _payload(email=target.email, affiliation_type=str(C.AffiliationType.MEMBER.id)),
        token=user_token,
    )

    assert_htmx_redirect(response, f"/groups/{group.id}")
    assert_flash(response, "User added to group.", category="success")

    session.expire_all()
    updated = session.get_one(Q.group.select(id=group.id))
    assert any(link.user_id == target.id for link in updated.user_links)


def test_submit_rejects_nonexistent_user(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    group = _group_with_owner(session, user)

    response = post_form(
        client,
        _submit_path(group.id),
        _payload(email="noone@example.com"),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "User with this email does not exist" in response.text


def test_submit_rejects_owner_affiliation_type(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """AffiliationType.OWNER is excluded via as_selectable_no_owner()."""
    group = _group_with_owner(session, user)
    target = _create_extra_user(session)

    response = post_form(
        client,
        _submit_path(group.id),
        _payload(
            email=target.email,
            affiliation_type=str(C.AffiliationType.OWNER.id),
        ),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "Owner affiliation type is not allowed" in response.text


def test_submit_rejects_duplicate_user(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    group = _group_with_owner(session, user)
    target = _create_extra_user(session)
    # Add target as member first
    group.user_links.append(
        Q.affiliation.create(user=target, group=group, type=C.AffiliationType.MEMBER)
    )
    session.save(group)
    _commit(session)

    response = post_form(
        client,
        _submit_path(group.id),
        _payload(email=target.email),
        token=user_token,
    )

    assert_form_invalid(response)
    assert "already in this group" in response.text


def test_submit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    group = _group_with_owner(session, user)
    target = _create_extra_user(session)

    response = post_form_csrf_mismatch(
        client,
        _submit_path(group.id),
        _payload(email=target.email),
        token=user_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")


def test_submit_unknown_is_404(
    client: TestClient,
    user_token: str,
):
    response = post_form(
        client,
        _submit_path(999999),
        _payload(email="test@example.com"),
        token=user_token,
    )

    assert response.status_code == 404