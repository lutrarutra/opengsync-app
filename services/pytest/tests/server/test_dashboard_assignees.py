"""Dashboard feed self-(un)assign: mutations answer 204 + flash (no redirect), and the
``feed-assignees`` fragment re-renders the controls in place.

The fragment shows an "Assign yourself" button while the insider isn't assigned, and
their own initials as an hx-delete button (unassign) once they are. Other assignees'
initials stay plain badges.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q, categories as C

from ..db.create_units import create_project, create_seq_request
from ._http import assert_flash, delete, get, post_form


def _project_paths(project_id: int, assignee_id: int) -> dict[str, str]:
    prefix = f"/htmx/projects/{project_id}"
    return {
        "assign": f"{prefix}/add-assignee",
        "unassign": f"{prefix}/remove-assignee/{assignee_id}",
        "fragment": f"{prefix}/feed-assignees",
    }


def _seq_request_paths(seq_request_id: int, assignee_id: int) -> dict[str, str]:
    prefix = f"/htmx/seq_requests/{seq_request_id}"
    return {
        "assign": f"{prefix}/self-assign",
        "unassign": f"{prefix}/remove-assignee/{assignee_id}",
        "fragment": f"{prefix}/feed-assignees",
    }


def _assert_unassigned_fragment(html: str, paths: dict[str, str]) -> None:
    assert 'class="feed-actions"' in html
    assert paths["fragment"] in html
    assert paths["assign"] in html
    assert "hx-delete" not in html


def _assert_assigned_fragment(html: str, paths: dict[str, str], initials: str) -> None:
    assert paths["assign"] not in html
    assert paths["unassign"] in html
    assert "Unassign yourself" in html
    assert f">{initials}</button>" in html


def test_project_feed_assign_unassign_roundtrip(
    client: TestClient, session: SyncSession, user, insider, insider_token: str,
):
    project = create_project(session, user)
    session.commit()
    paths = _project_paths(project.id, insider.id)

    response = get(client, paths["fragment"], insider_token, htmx=True)
    assert response.status_code == 200
    _assert_unassigned_fragment(response.text, paths)

    response = post_form(client, paths["assign"], {}, insider_token, htmx=True)
    assert response.status_code == 204
    assert "HX-Redirect" not in response.headers
    assert_flash(response, "Assignee Added!", "success")

    session.expire_all()
    assert insider in session.get_one(Q.project.select(id=project.id)).assignees

    response = get(client, paths["fragment"], insider_token, htmx=True)
    _assert_assigned_fragment(response.text, paths, insider.initials)

    response = delete(client, paths["unassign"], insider_token, htmx=True)
    assert response.status_code == 204
    assert "HX-Redirect" not in response.headers

    response = get(client, paths["fragment"], insider_token, htmx=True)
    _assert_unassigned_fragment(response.text, paths)


def test_seq_request_feed_assign_unassign_roundtrip(
    client: TestClient, session: SyncSession, user, insider, insider_token: str,
):
    seq_request = create_seq_request(session, user)
    session.commit()
    paths = _seq_request_paths(seq_request.id, insider.id)

    response = get(client, paths["fragment"], insider_token, htmx=True)
    assert response.status_code == 200
    _assert_unassigned_fragment(response.text, paths)

    response = post_form(client, paths["assign"], {}, insider_token, htmx=True)
    assert response.status_code == 204
    assert "HX-Redirect" not in response.headers
    assert_flash(response, "Assignee Added!", "success")

    response = get(client, paths["fragment"], insider_token, htmx=True)
    _assert_assigned_fragment(response.text, paths, insider.initials)

    response = delete(client, paths["unassign"], insider_token, htmx=True)
    assert response.status_code == 204

    response = get(client, paths["fragment"], insider_token, htmx=True)
    _assert_unassigned_fragment(response.text, paths)


def test_other_assignee_badge_is_not_clickable(
    client: TestClient, session: SyncSession, user, insider, admin, insider_token: str,
):
    project = create_project(session, user)
    project.assignees.append(admin)
    session.commit()
    paths = _project_paths(project.id, insider.id)

    response = get(client, paths["fragment"], insider_token, htmx=True)

    assert response.status_code == 200
    assert f">{admin.initials}</span>" in response.text
    assert "hx-delete" not in response.text


def test_feed_fragment_requires_insider(client: TestClient, session: SyncSession, user, user_token: str):
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    session.commit()

    assert get(client, f"/htmx/projects/{project.id}/feed-assignees", user_token, htmx=True).status_code == 403
    assert get(client, f"/htmx/seq_requests/{seq_request.id}/feed-assignees", user_token, htmx=True).status_code == 403


def test_paging_banner_does_not_leak_target_into_assignee_controls(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    """The last card of a full page carries the infinite-scroll hx-target; without
    hx-disinherit the card's assignee controls swapped into the feed spinner instead."""
    for _ in range(10):
        create_project(session, user).status = C.ProjectStatus.PROCESSING
        create_seq_request(session, user).status = C.SeqRequestStatus.SUBMITTED
    session.commit()

    for path in ("/htmx/projects/render-feed", "/htmx/seq_requests/render-feed"):
        response = get(client, path, insider_token, htmx=True)
        assert response.status_code == 200
        assert 'hx-trigger="intersect once"' in response.text
        assert 'hx-disinherit="*"' in response.text
