"""Search routes of SearchableInputFields: JSON pages of {id, name, header?, description?, data?}."""

import uuid

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q

from ..db.create_units import create_group, create_project
from ._http import get

PAGE_SIZE = 20

SEARCH_URLS = [
    "/htmx/projects/search",
    "/htmx/users/search",
    "/htmx/groups/search",
    "/htmx/pools/search",
    "/htmx/libraries/search",
    "/htmx/seq_requests/search",
    "/htmx/experiments/search",
    "/htmx/sequencers/search",
    "/htmx/kits/search-kits",
    "/htmx/index_kits/search-index_kits",
]


@pytest.mark.parametrize("url", SEARCH_URLS)
@pytest.mark.parametrize("params", [{}, {"word": "zz"}, {"selected_id": 1}, {"page": 3}])
def test_search_routes_return_option_pages(client: TestClient, insider_token: str, url: str, params: dict):
    response = get(client, url, insider_token, params=params)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert isinstance(body["options"], list)
    assert isinstance(body["has_more"], bool)
    for option in body["options"]:
        assert isinstance(option["id"], int) and isinstance(option["name"], str)
        assert set(option) <= {"id", "name", "header", "description", "data"}


def test_project_search_option_shows_identifier_title_and_status(client: TestClient, session: SyncSession, user, user_token: str):
    project = create_project(session, user)
    project.identifier = "BSA_4242"
    session.commit()

    response = get(client, "/htmx/projects/search", user_token, params={"word": project.title})

    option = next(option for option in response.json()["options"] if option["id"] == project.id)
    assert option == {
        "id": project.id,
        "name": project.title,
        "header": "BSA_4242",
        "description": f"{project.status.label} {project.status.icon}",
    }


def test_project_search_selected_id_returns_only_that_project(client: TestClient, session: SyncSession, user, user_token: str):
    selected = create_project(session, user)
    create_project(session, user)
    session.commit()

    response = get(client, "/htmx/projects/search", user_token, params={"selected_id": selected.id})

    assert [option["id"] for option in response.json()["options"]] == [selected.id]


def test_project_search_hides_other_users_projects_from_clients(
    client: TestClient, session: SyncSession, user, user_2, user_token: str, insider_token: str,
):
    own = create_project(session, user)
    foreign = create_project(session, user_2)
    session.commit()

    seen = {option["id"] for option in get(client, "/htmx/projects/search", user_token).json()["options"]}
    assert own.id in seen and foreign.id not in seen

    by_id = get(client, "/htmx/projects/search", user_token, params={"selected_id": foreign.id}).json()
    assert by_id["options"] == []

    seen = {option["id"] for option in get(client, "/htmx/projects/search", insider_token).json()["options"]}
    assert {own.id, foreign.id} <= seen


def test_project_search_pages_through_results(client: TestClient, session: SyncSession, user, user_token: str):
    prefix = f"page-{uuid.uuid4().hex[:8]}"
    for i in range(PAGE_SIZE + 5):
        session.save(Q.project.create(title=f"{prefix}-{i:02d}", description="d", owner_id=user.id), flush=True)
    session.commit()

    first = get(client, "/htmx/projects/search", user_token, params={"word": prefix, "page": 0}).json()
    second = get(client, "/htmx/projects/search", user_token, params={"word": prefix, "page": 1}).json()

    assert len(first["options"]) == PAGE_SIZE and first["has_more"] is True
    assert len(second["options"]) == 5 and second["has_more"] is False
    names = [option["name"] for option in first["options"] + second["options"]]
    assert sorted(names) == sorted(f"{prefix}-{i:02d}" for i in range(PAGE_SIZE + 5))


def test_user_search_option_carries_email(client: TestClient, user_2, insider_token: str):
    response = get(client, "/htmx/users/search", insider_token, params={"selected_id": user_2.id})

    assert response.json()["options"] == [{
        "id": user_2.id,
        "name": user_2.name,
        "header": user_2.role.icon,
        "description": user_2.email,
        "data": {"email": user_2.email},
    }]


def test_group_search_hides_groups_of_others_from_clients(client: TestClient, session: SyncSession, user_token: str, insider_token: str):
    group = create_group(session)
    session.commit()

    assert group.id not in {option["id"] for option in get(client, "/htmx/groups/search", user_token).json()["options"]}
    assert group.id in {
        option["id"] for option in get(client, "/htmx/groups/search", insider_token, params={"selected_id": group.id}).json()["options"]
    }


def test_search_requires_login(client: TestClient):
    assert get(client, "/htmx/projects/search").status_code in (302, 303, 401, 403)
