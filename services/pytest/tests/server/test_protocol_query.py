"""Protocol options for the spreadsheet QueryColumn: JSON pages of {id, name}."""

import uuid

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, categories as C, queries as Q

from ..db.create_units import create_protocol
from ._http import get


QUERY_URL = "/htmx/protocols/query"


def _create_named_protocols(session: SyncSession, prefix: str, count: int) -> list:
    protocols = [
        session.save(Q.protocol.create(name=f"{prefix}-{i:02d}", service_type=C.ServiceType.CUSTOM), flush=True)
        for i in range(count)
    ]
    session.commit()
    return protocols


def test_query_returns_options(client: TestClient, session: SyncSession, user_token: str):
    protocol = create_protocol(session)
    session.commit()

    response = get(client, QUERY_URL, user_token, params={"word": protocol.name})

    assert response.status_code == 200
    body = response.json()
    assert body["options"][0] == {"id": protocol.id, "name": protocol.name}
    assert isinstance(body["has_more"], bool)


def test_query_pages_through_matches(client: TestClient, session: SyncSession, user_token: str):
    prefix = f"query-{uuid.uuid4().hex[:12]}"
    protocols = _create_named_protocols(session, prefix, 25)

    first = get(client, QUERY_URL, user_token, params={"word": prefix, "page": 0}).json()
    second = get(client, QUERY_URL, user_token, params={"word": prefix, "page": 1}).json()

    # Names containing the word come before similar names
    assert len(first["options"]) == 20
    assert first["has_more"] is True
    assert all(option["name"].startswith(prefix) for option in first["options"])
    names = [option["name"] for option in first["options"] + second["options"] if option["name"].startswith(prefix)]
    assert sorted(names) == sorted(protocol.name for protocol in protocols)


def test_query_without_word_lists_protocols_by_name(client: TestClient, session: SyncSession, user_token: str):
    create_protocol(session)
    session.commit()

    body = get(client, QUERY_URL, user_token, params={"page": 0}).json()

    names = [option["name"] for option in body["options"]]
    assert names
    assert names == sorted(names)


def test_query_past_last_page_is_empty(client: TestClient, session: SyncSession, user_token: str):
    create_protocol(session)
    session.commit()

    body = get(client, QUERY_URL, user_token, params={"page": 100_000}).json()

    assert body == {"options": [], "has_more": False}


def test_query_matches_like_wildcards_literally(client: TestClient, session: SyncSession, user_token: str):
    prefix = f"query-{uuid.uuid4().hex[:12]}"
    _create_named_protocols(session, prefix, 1)

    body = get(client, QUERY_URL, user_token, params={"word": "%"}).json()

    assert all("%" in option["name"] for option in body["options"])
