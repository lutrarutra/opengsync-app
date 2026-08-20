"""HTTP form submission: CSRF, persist, and permission checks."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q, categories as C

from ..db.create_units import create_seq_request, create_group
from ._http import auth, post_form, get


def _commit(session: SyncSession) -> None:
    session.commit()


def test_add_user_to_group_client_forbidden(
    client: TestClient, session: SyncSession, user, user_2, user_token,
):
    group = create_group(session)
    _commit(session)

    assert get(client, f"/htmx/groups/{group.id}/add-user", user_token).status_code == 403

    response = post_form(
        client,
        f"/htmx/groups/{group.id}/add-user",
        {"email": user_2.email, "affiliation_type": str(C.AffiliationType.MEMBER.id)},
        token=user_token,
    )
    assert response.status_code == 403
    assert session.first(Q.affiliation.select(user_id=user_2.id, group_id=group.id)) is None


def test_add_user_to_group_insider_persists(
    client: TestClient, session: SyncSession, user_2, insider_token,
):
    group = create_group(session)
    _commit(session)

    response = post_form(
        client,
        f"/htmx/groups/{group.id}/add-user",
        {"email": user_2.email, "affiliation_type": str(C.AffiliationType.MEMBER.id)},
        token=insider_token,
    )
    assert response.status_code == 204
    assert "HX-Redirect" in response.headers

    session.expire_all()
    assert session.first(Q.affiliation.select(user_id=user_2.id, group_id=group.id)) is not None


def test_add_user_to_group_unknown_email_rerenders(
    client: TestClient, session: SyncSession, insider_token,
):
    group = create_group(session)
    _commit(session)

    response = post_form(
        client,
        f"/htmx/groups/{group.id}/add-user",
        {"email": "missing@example.com", "affiliation_type": str(C.AffiliationType.MEMBER.id)},
        token=insider_token,
    )
    assert response.status_code == 202
    assert session.count(Q.affiliation.select(group_id=group.id)) == 0


def test_add_user_to_group_csrf_mismatch_rerenders(
    client: TestClient, session: SyncSession, user_2, insider_token,
):
    group = create_group(session)
    _commit(session)

    client.cookies.set("csrf_token", "cookie-token")
    response = client.post(
        f"/htmx/groups/{group.id}/add-user",
        data={
            "email": user_2.email,
            "affiliation_type": str(C.AffiliationType.MEMBER.id),
            "csrf_token": "body-token",
        },
        headers=auth(insider_token),
        follow_redirects=False,
    )
    assert response.status_code == 202
    assert session.first(Q.affiliation.select(user_id=user_2.id, group_id=group.id)) is None


def test_comment_owner_persists(
    client: TestClient, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(
        client,
        "/htmx/comments/comment",
        {"comment": "hello from owner"},
        token=user_token,
        params={"seq_request_id": seq_request.id},
    )
    assert response.status_code == 204
    session.expire_all()
    comments = session.get_all(Q.comment.select(seq_request_id=seq_request.id), limit=None)
    assert len(comments) == 1
    assert comments[0].text == "hello from owner"


def test_comment_stranger_forbidden(
    client: TestClient, session: SyncSession, user, user_2_token,
):
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(
        client,
        "/htmx/comments/comment",
        {"comment": "nope"},
        token=user_2_token,
        params={"seq_request_id": seq_request.id},
    )
    assert response.status_code == 403
    assert session.count(Q.comment.select(seq_request_id=seq_request.id)) == 0


def test_comment_insider_allowed(
    client: TestClient, session: SyncSession, user, insider_token,
):
    seq_request = create_seq_request(session, user)
    _commit(session)

    response = post_form(
        client,
        "/htmx/comments/comment",
        {"comment": "staff note"},
        token=insider_token,
        params={"seq_request_id": seq_request.id},
    )
    assert response.status_code == 204
    session.expire_all()
    assert session.count(Q.comment.select(seq_request_id=seq_request.id)) == 1


def test_comment_get_requires_write(
    client: TestClient, session: SyncSession, user, user_token, user_2_token,
):
    seq_request = create_seq_request(session, user)
    _commit(session)

    owner = get(
        client, "/htmx/comments/comment", user_token,
        params={"seq_request_id": seq_request.id},
    )
    assert owner.status_code not in (303, 401, 403)

    stranger = get(
        client, "/htmx/comments/comment", user_2_token,
        params={"seq_request_id": seq_request.id},
    )
    assert stranger.status_code == 403
