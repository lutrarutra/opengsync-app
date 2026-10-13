"""Affiliation table: user (groups tab) and group (members tab) contexts."""

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C

from ..db.create_units import create_group
from ._http import get

TABLE_PATH = "/htmx/affiliations/render-table-page"


@pytest.fixture
def lab(session: SyncSession, user, user_2) -> models.Group:
    group = create_group(session)
    session.add(models.links.UserAffiliation(user_id=user.id, group_id=group.id, affiliation_type=C.AffiliationType.OWNER))
    session.add(models.links.UserAffiliation(user_id=user_2.id, group_id=group.id, affiliation_type=C.AffiliationType.MEMBER))
    session.commit()
    return group


def test_user_can_view_own_groups(client: TestClient, user_token: str, user, lab):
    response = get(client, TABLE_PATH, user_token, params={"user_id": user.id}, htmx=True)

    assert response.status_code == 200
    assert 'id="user-affiliation-table"' in response.text
    assert lab.name in response.text
    assert f"/groups/{lab.id}?from=user%40{user.id}" in response.text


def test_user_groups_table_without_affiliations(client: TestClient, user_token: str, user):
    response = get(client, TABLE_PATH, user_token, params={"user_id": user.id}, htmx=True)

    assert response.status_code == 200
    assert 'id="user-affiliation-table"' in response.text


def test_user_cannot_view_another_users_groups(client: TestClient, user_token: str, user_2, lab):
    response = get(client, TABLE_PATH, user_token, params={"user_id": user_2.id}, htmx=True)

    assert response.status_code == 403


def test_insider_can_view_another_users_groups(client: TestClient, insider_token: str, user, lab):
    response = get(client, TABLE_PATH, insider_token, params={"user_id": user.id}, htmx=True)

    assert response.status_code == 200
    assert lab.name in response.text


def test_group_member_can_view_group_members(client: TestClient, user_2_token: str, user, user_2, lab):
    response = get(client, TABLE_PATH, user_2_token, params={"group_id": lab.id}, htmx=True)

    assert response.status_code == 200
    assert 'id="group-user-table"' in response.text
    assert user.email in response.text
    assert user_2.email in response.text


def test_affiliation_table_requires_context(client: TestClient, user_token: str):
    response = get(client, TABLE_PATH, user_token, htmx=True)

    assert response.status_code == 400
