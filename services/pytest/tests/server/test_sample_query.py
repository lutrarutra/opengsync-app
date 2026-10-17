"""Sample options for the spreadsheet QueryColumn: JSON pages of {id, name} of one project's reusable samples."""

import uuid

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, categories as C, queries as Q

from ._http import get


QUERY_URL = "/htmx/samples/query"


def _project_with_samples(session: SyncSession, user, statuses: dict[str, C.SampleStatus]):
    title = f"Sample Query Project {uuid.uuid4().hex[:8]}"
    project = session.save(Q.project.create(title=title, description="query", owner_id=user.id), flush=True)
    samples = {
        name: session.save(Q.sample.create(name=name, project_id=project.id, owner_id=user.id, status=status), flush=True)
        for name, status in statuses.items()
    }
    session.commit()
    return project, samples


def test_query_lists_project_samples_by_name(client: TestClient, session: SyncSession, user, user_token: str):
    project, samples = _project_with_samples(session, user, {
        "Query_B": C.SampleStatus.DRAFT, "Query_A": C.SampleStatus.STORED,
    })
    _project_with_samples(session, user, {"Query_Other": C.SampleStatus.DRAFT})  # samples of other projects are not listed

    body = get(client, QUERY_URL, user_token, params={"project_id": project.id}).json()

    assert body == {
        "options": [
            {"id": samples["Query_A"].id, "name": "Query_A"},
            {"id": samples["Query_B"].id, "name": "Query_B"},
        ],
        "has_more": False,
    }


def test_query_matches_word_and_skips_rejected(client: TestClient, session: SyncSession, user, user_token: str):
    project, samples = _project_with_samples(session, user, {
        "Liver_1": C.SampleStatus.DRAFT, "Liver_2": C.SampleStatus.REJECTED, "Brain_1": C.SampleStatus.DRAFT,
    })

    body = get(client, QUERY_URL, user_token, params={"project_id": project.id, "word": "Liver"}).json()

    names = [option["name"] for option in body["options"]]
    assert names[0] == "Liver_1"
    assert "Liver_2" not in names  # rejected samples cannot be reused


def test_query_requires_project_access(client: TestClient, session: SyncSession, user, user_2_token: str):
    project, _ = _project_with_samples(session, user, {"Private_1": C.SampleStatus.DRAFT})

    response = get(client, QUERY_URL, user_2_token, params={"project_id": project.id})

    assert response.status_code == 403


def test_query_requires_project(client: TestClient, user_token: str):
    response = get(client, QUERY_URL, user_token)

    assert response.status_code != 200
