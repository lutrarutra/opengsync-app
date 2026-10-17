"""Feature kit options for the spreadsheet QueryColumn: JSON pages of {id, "[identifier] name"}."""

import json
import uuid

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, categories as C, queries as Q

from ._http import get


QUERY_URL = "/htmx/feature_kits/query"
ANTIBODY = json.dumps([C.FeatureType.ANTIBODY.id])


def _create_kits(session: SyncSession, prefix: str, count: int, type: C.FeatureType = C.FeatureType.ANTIBODY) -> list:
    kits = [
        session.save(Q.feature_kit.create(
            name=f"{prefix}-{type.name}-{i:02d}", identifier=f"ID{uuid.uuid4().hex[:12]}", type=type,
        ), flush=True)
        for i in range(count)
    ]
    session.commit()
    return kits


def test_query_returns_identifier_and_name(client: TestClient, session: SyncSession, user_token: str):
    kit, = _create_kits(session, f"kit-{uuid.uuid4().hex[:12]}", 1)

    body = get(client, QUERY_URL, user_token, params={"word": kit.name}).json()

    assert body["options"][0] == {"id": kit.id, "name": f"[{kit.identifier}] {kit.name}"}
    assert isinstance(body["has_more"], bool)


def test_query_matches_identifier(client: TestClient, session: SyncSession, user_token: str):
    kit, = _create_kits(session, f"kit-{uuid.uuid4().hex[:12]}", 1)

    body = get(client, QUERY_URL, user_token, params={"word": kit.identifier}).json()

    assert [option["id"] for option in body["options"]][:1] == [kit.id]


def test_query_filters_by_type(client: TestClient, session: SyncSession, user_token: str):
    prefix = f"kit-{uuid.uuid4().hex[:12]}"
    antibody, = _create_kits(session, prefix, 1)
    cmo, = _create_kits(session, prefix, 1, type=C.FeatureType.CMO)

    unfiltered = get(client, QUERY_URL, user_token, params={"word": prefix}).json()
    filtered = get(client, QUERY_URL, user_token, params={"word": prefix, "type_in": ANTIBODY}).json()

    assert {antibody.id, cmo.id} <= {option["id"] for option in unfiltered["options"]}
    ids = {option["id"] for option in filtered["options"]}
    assert antibody.id in ids and cmo.id not in ids


def test_query_pages_through_matches(client: TestClient, session: SyncSession, user_token: str):
    prefix = f"kit-{uuid.uuid4().hex[:12]}"
    kits = _create_kits(session, prefix, 25)

    first = get(client, QUERY_URL, user_token, params={"word": prefix, "page": 0}).json()
    second = get(client, QUERY_URL, user_token, params={"word": prefix, "page": 1}).json()

    assert len(first["options"]) == 20
    assert first["has_more"] is True
    ids = {option["id"] for option in first["options"] + second["options"]}
    assert {kit.id for kit in kits} <= ids


def test_query_past_last_page_is_empty(client: TestClient, session: SyncSession, user_token: str):
    _create_kits(session, f"kit-{uuid.uuid4().hex[:12]}", 1)

    body = get(client, QUERY_URL, user_token, params={"page": 100_000}).json()

    assert body == {"options": [], "has_more": False}

