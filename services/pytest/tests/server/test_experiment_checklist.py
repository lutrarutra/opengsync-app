"""Experiment checklist: the 'Requests Accepted' step lists the experiment's requests."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, categories as C

from ..db.create_units import create_experiment, create_library, create_seq_request
from ._http import get


def test_checklist_lists_experiment_seq_requests(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S4_STD)
    accepted_request = create_seq_request(session, user)
    accepted_request.status = C.SeqRequestStatus.ACCEPTED
    draft_request = create_seq_request(session, user)
    unrelated_request = create_seq_request(session, user)
    for seq_request in (accepted_request, draft_request):
        create_library(session, user, seq_request).experiment_id = experiment.id
    create_library(session, user, unrelated_request)
    session.commit()

    response = get(client, f"/htmx/experiments/{experiment.id}/checklist", insider_token, htmx=True)

    assert response.status_code == 200
    assert "⚠️ Requests Accepted" in response.text
    assert accepted_request.name in response.text
    assert draft_request.name in response.text
    assert unrelated_request.name not in response.text
    assert response.text.count('class="table-warning"') == 1

    draft_request.status = C.SeqRequestStatus.SAMPLES_RECEIVED
    session.commit()

    response = get(client, f"/htmx/experiments/{experiment.id}/checklist", insider_token, htmx=True)

    assert response.status_code == 200
    assert "✅ Requests Accepted" in response.text
    assert 'class="table-warning"' not in response.text
