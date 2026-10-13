"""User page projects tab: lists only projects the user owns."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C

from ..db.create_units import create_group, create_project
from ._http import get

TABLE_PATH = "/htmx/projects/render-table-page"


def test_user_projects_tab_lists_only_owned_projects(
    client: TestClient, session: SyncSession, user_token: str, user, user_2,
):
    group = create_group(session)
    session.add(models.links.UserAffiliation(user_id=user.id, group_id=group.id, affiliation_type=C.AffiliationType.MEMBER))
    owned = create_project(session, user)
    group_project = create_project(session, user_2)
    group_project.group_id = group.id
    session.commit()

    response = get(client, TABLE_PATH, user_token, params={"user_id": user.id}, htmx=True)

    assert response.status_code == 200
    assert owned.title in response.text
    assert group_project.title not in response.text


def test_user_cannot_view_another_users_projects(client: TestClient, user_token: str, user_2):
    response = get(client, TABLE_PATH, user_token, params={"user_id": user_2.id}, htmx=True)

    assert response.status_code == 403
