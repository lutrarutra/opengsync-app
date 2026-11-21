"""Entity filters of the htmx tables only offer and apply objects the viewer may see
(server/components/tables/visibility.py).

A client filtering libraries by owner, request or group is offered only the objects that occur in the rows
they can see and that they may see themselves: themselves and their group's members, their own and their
group's requests, their groups. An id of anything else in the URL (``owner_in=<someone else>``) is dropped
silently: no chip, no name in the page, no filtering. Options requests run the route's permission checks.
"""
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ..db.create_units import create_group, create_library, create_seq_request, create_user
from ..conftest import _login_token
from ._http import get

PATH = "/htmx/libraries/render-table-page"


def _setup(session: SyncSession, user: models.User, user_2: models.User):
    """``user`` and ``colleague`` share a group (and its requests); ``user_2`` is outside of it."""
    colleague = create_user(session)
    user.first_name, colleague.first_name, user_2.first_name = "Ursula", "Colette", "Ottokar"
    group = create_group(session)
    group.name = "Zebrafish Lab"
    session.add(Q.affiliation.create(user=user, group=group, type=C.AffiliationType.OWNER))
    session.add(Q.affiliation.create(user=colleague, group=group, type=C.AffiliationType.MEMBER))

    requests, libraries = {}, {}
    for key, owner, shared in [("mine", user, True), ("colleague", colleague, True), ("outside", user_2, False)]:
        seq_request = create_seq_request(session, owner)
        seq_request.name = f"Request {key}"
        seq_request.group = group if shared else None
        library = create_library(session, owner, seq_request)
        library.name = f"LIB_{key.upper()}"
        requests[key], libraries[key] = seq_request, library
    session.commit()
    return colleague, group, requests, libraries


def _options(client: TestClient, token: str, field: str, **params) -> set[int]:
    response = get(client, PATH, token=token, htmx=True, params={"options": field, **params})
    assert response.status_code == 200, response.text[:300]
    return {option["id"] for option in response.json()["options"]}


def _html(client: TestClient, token: str, **params) -> str:
    response = get(client, PATH, token=token, htmx=True, params=params)
    assert response.status_code == 200, response.text[:300]
    return response.text


def test_client_is_offered_only_visible_owners_requests_and_groups(
    client: TestClient, session: SyncSession, user, user_2, user_token: str,
):
    colleague, group, requests, _ = _setup(session, user, user_2)

    assert _options(client, user_token, "owner") == {user.id, colleague.id}
    assert _options(client, user_token, "seq_request") == {requests["mine"].id, requests["colleague"].id}
    assert _options(client, user_token, "group") == {group.id}
    # the type-ahead narrows the visible options, it never widens them
    assert _options(client, user_token, "owner", word="Ottokar") == set()
    assert _options(client, user_token, "owner", word="Colette") == {colleague.id}


def test_insider_is_offered_everything(client: TestClient, session: SyncSession, user, user_2, insider_token: str):
    colleague, _, requests, _ = _setup(session, user, user_2)
    assert {user.id, colleague.id, user_2.id} <= _options(client, insider_token, "owner")
    assert {r.id for r in requests.values()} <= _options(client, insider_token, "seq_request")


def test_invisible_ids_are_dropped_silently(client: TestClient, session: SyncSession, user, user_2, user_token: str):
    _, _, requests, libraries = _setup(session, user, user_2)

    html = _html(client, user_token, owner_in=str(user_2.id), seq_request_in=str(requests["outside"].id))
    assert "otable-chip-value" not in html  # no chip
    assert "Ottokar" not in html and requests["outside"].name not in html  # no names leak
    assert libraries["mine"].name in html and libraries["colleague"].name in html  # nothing filtered
    assert libraries["outside"].name not in html


def test_visible_ids_filter_and_combine_with_search_and_enum_filters(
    client: TestClient, session: SyncSession, user, user_2, user_token: str,
):
    colleague, _, _, libraries = _setup(session, user, user_2)

    html = _html(client, user_token, owner_in=str(colleague.id))
    assert libraries["colleague"].name in html and libraries["mine"].name not in html
    assert "Owner is" in html and "Colette" in html

    assert libraries["colleague"].name in _html(client, user_token, owner_in=str(colleague.id), q="LIB_COLL")
    assert libraries["colleague"].name not in _html(client, user_token, owner_in=str(colleague.id), q="Xylophone")

    status = libraries["colleague"].status
    other = next(s for s in C.LibraryStatus.as_list() if s != status)
    assert libraries["colleague"].name in _html(client, user_token, owner_in=str(colleague.id), status_in=str(status.id))
    assert libraries["colleague"].name not in _html(client, user_token, owner_in=str(colleague.id), status_in=str(other.id))


def test_options_run_the_routes_permission_checks(client: TestClient, session: SyncSession, user, user_2, user_token: str):
    _, _, requests, _ = _setup(session, user, user_2)
    response = get(client, PATH, token=user_token, htmx=True, params={
        "options": "owner", "seq_request_id": requests["outside"].id,
    })
    assert response.status_code == 403


def test_options_come_from_the_viewers_rows(client: TestClient, session: SyncSession, user, user_2, user_token: str):
    _setup(session, user, user_2)
    other = create_user(session)
    session.commit()
    # a client without libraries sees no rows, so there is no owner to offer, not even someone else's
    response = get(client, PATH, token=_login_token(other), htmx=True, params={"options": "owner"})
    assert response.status_code == 200
    assert response.json()["options"] == []


def test_assignee_filter_offers_the_staff_on_the_customers_rows(
    client: TestClient, session: SyncSession, user, user_2, insider, admin, user_token: str,
):
    """Staff are not visible to customers by the user rule, but the ones assigned to the customer's requests
    are shown on those rows anyway, so the assignee filter offers exactly them (Entity(from_rows=True))."""
    mine = create_seq_request(session, user)
    mine.name = "MY_ASSIGNED_REQUEST"
    others = create_seq_request(session, user_2)
    others.name = "SOMEONE_ELSES_REQUEST"
    mine.assignees.append(insider)
    others.assignees.append(admin)  # assigned to a request the customer cannot see
    session.commit()

    path = "/htmx/seq_requests/render-table-page"
    response = get(client, path, token=user_token, htmx=True, params={"options": "assignees"})
    assert {o["id"] for o in response.json()["options"]} == {insider.id}

    html = get(client, path, token=user_token, htmx=True, params={"assignees_in": str(insider.id)}).text
    assert "MY_ASSIGNED_REQUEST" in html and "Assignees is" in html
    # the other request's assignee is not accepted from the URL: no chip, no name, nothing filtered
    html = get(client, path, token=user_token, htmx=True, params={"assignees_in": str(admin.id)}).text
    assert "Assignees is" not in html and admin.email not in html and "MY_ASSIGNED_REQUEST" in html
