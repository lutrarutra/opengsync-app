"""Experiment checklist: the 'Requests Accepted' step lists the experiment's requests."""

import sqlalchemy as sa
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ..db.create_units import create_experiment, create_library, create_pool, create_seq_request
from ._http import get, post_form, assert_htmx_redirect


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


# ── Check Barcode Clashes: required, checked by hand ─────────────────────────

def _barcode_step(client: TestClient, experiment_id: int, action: str, token: str, step: str = "check_barcode_clashes"):
    return post_form(client, f"/htmx/experiments/{experiment_id}/{action}/{step}", {}, token=token, htmx=True)


def _logs(session: SyncSession, experiment_id: int) -> list[models.ChecklistLog]:
    session.expire_all()
    return list(session.execute(
        sa.select(models.ChecklistLog).where(models.ChecklistLog.experiment_id == experiment_id).order_by(models.ChecklistLog.id)
    ).scalars())


def test_barcode_clashes_needs_pools(client: TestClient, session: SyncSession, user, insider_token: str):
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S4_STD)
    session.commit()

    response = get(client, f"/htmx/experiments/{experiment.id}/checklist", insider_token, htmx=True)
    assert "❗ Check Barcode Clashes" in response.text
    assert _barcode_step(client, experiment.id, "checklist-check", insider_token).status_code == 400
    assert _logs(session, experiment.id) == []


def test_barcode_clashes_check_and_uncheck(client: TestClient, session: SyncSession, user, insider, insider_token: str):
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S4_STD)
    create_pool(session, user, create_seq_request(session, user)).experiment_id = experiment.id
    session.commit()

    response = get(client, f"/htmx/experiments/{experiment.id}/checklist", insider_token, htmx=True)
    assert "⚠️ Check Barcode Clashes" in response.text

    assert_htmx_redirect(_barcode_step(client, experiment.id, "checklist-check", insider_token), f"/experiments/{experiment.id}")
    # Already checked: nothing changes, nothing is logged
    assert_htmx_redirect(_barcode_step(client, experiment.id, "checklist-check", insider_token), f"/experiments/{experiment.id}")

    response = get(client, f"/htmx/experiments/{experiment.id}/checklist", insider_token, htmx=True)
    assert "✅ Check Barcode Clashes" in response.text
    assert f"checked by {insider.name}" in response.text
    assert 'data-bs-target="#experiment-check_barcode_clashes-history"' in response.text

    assert_htmx_redirect(_barcode_step(client, experiment.id, "checklist-uncheck", insider_token), f"/experiments/{experiment.id}")

    logs = _logs(session, experiment.id)
    assert [(log.step, log.checked, log.actor_id) for log in logs] == [
        ("check_barcode_clashes", True, insider.id), ("check_barcode_clashes", False, insider.id),
    ]
    assert all(log.checklist_type == C.ChecklistType.EXPERIMENT for log in logs)
    assert session.get_one(Q.experiment.select(id=experiment.id)).get_checklist()["barcode_clashes_checked"] is False


def test_unknown_experiment_step_rejected(client: TestClient, session: SyncSession, user, insider_token: str):
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S4_STD)
    create_pool(session, user, create_seq_request(session, user)).experiment_id = experiment.id
    session.commit()

    for action in ("checklist-check", "checklist-uncheck"):
        assert _barcode_step(client, experiment.id, action, insider_token, step="not_a_step").status_code == 400
    assert _logs(session, experiment.id) == []


def test_experiment_checklist_steps_need_insider(client: TestClient, session: SyncSession, user, user_token: str):
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S4_STD)
    create_pool(session, user, create_seq_request(session, user)).experiment_id = experiment.id
    session.commit()

    assert _barcode_step(client, experiment.id, "checklist-check", user_token).status_code in (401, 403)
    assert _logs(session, experiment.id) == []
