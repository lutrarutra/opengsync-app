"""SelectExperimentPoolsAction: render, permissions, and pool linking.

Access control:
- **GET (Begin)** and **POST (Submit)** both require ``require_insider``.
"""

import json

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_experiment, create_pool, create_seq_request
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

PREFIX = "/htmx/experiments"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"
WORKFLOW = C.ExperimentWorkFlow.NOVASEQ_6K_S4_STD


def _path(experiment_id: int) -> str:
    return f"{PREFIX}/{experiment_id}/select-pools"


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "selected_pool_ids": json.dumps([1]),
    }
    data.update({key: str(value) for key, value in overrides.items()})
    return data


def _commit(session: SyncSession) -> None:
    session.commit()


def _reload(session: SyncSession, model) -> None:
    session.expire_all()


# ── Render (GET) ─────────────────────────────────────────────────────────────


def test_render_get_allows_insider(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """An insider can fetch the select-pools form for a valid experiment."""
    experiment = create_experiment(session, user, WORKFLOW)
    _commit(session)

    response = get(client, _path(experiment.id), insider_token, htmx=True)

    assert response.status_code == 200
    assert 'name="selected_pool_ids"' in response.text
    assert 'name="csrf_token"' in response.text


def test_render_get_denies_client(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """A CLIENT user (non-insider) is denied access to the GET route."""
    experiment = create_experiment(session, user, WORKFLOW)
    _commit(session)

    response = get(client, _path(experiment.id), user_token, htmx=True)

    assert response.status_code == 403


def test_render_get_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    """A non-existent experiment id returns 404."""
    response = get(client, _path(999999), insider_token, htmx=True)

    assert response.status_code == 404


# ── Submit (POST) ────────────────────────────────────────────────────────────


def test_submit_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """A CLIENT user is denied on POST even with a valid payload."""
    experiment = create_experiment(session, user, WORKFLOW)
    _commit(session)

    response = post_form(
        client,
        _path(experiment.id),
        _payload(),
        token=user_token,
    )

    assert response.status_code == 403


def test_submit_links_pools_to_experiment(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """A valid POST by an insider links the selected pools to the experiment."""
    experiment = create_experiment(session, user, WORKFLOW)
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    pool.status = C.PoolStatus.STORED
    _commit(session)

    response = post_form(
        client,
        _path(experiment.id),
        _payload(selected_pool_ids=json.dumps([pool.id])),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert_flash(response, "Pools linked to experiment", category="success")

    _reload(session, experiment)
    loaded_pool = session.get_one(Q.pool.select(id=pool.id))
    assert loaded_pool.experiment_id == experiment.id


def test_submit_skips_already_linked_pools(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """A pool already linked to the same experiment is skipped without error."""
    experiment = create_experiment(session, user, WORKFLOW)
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    pool.status = C.PoolStatus.STORED
    pool.experiment_id = experiment.id
    _commit(session)

    response = post_form(
        client,
        _path(experiment.id),
        _payload(selected_pool_ids=json.dumps([pool.id])),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert_flash(response, "Pools linked to experiment", category="success")

    _reload(session, experiment)
    loaded_pool = session.get_one(Q.pool.select(id=pool.id))
    assert loaded_pool.experiment_id == experiment.id


def test_submit_empty_selection(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """An empty pool selection (``[]``) is accepted since the field is optional."""
    experiment = create_experiment(session, user, WORKFLOW)
    _commit(session)

    response = post_form(
        client,
        _path(experiment.id),
        _payload(selected_pool_ids=json.dumps([])),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert_flash(response, "Pools linked to experiment", category="success")


def test_submit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """A CSRF mismatch re-renders the form with an error flash."""
    experiment = create_experiment(session, user, WORKFLOW)
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    pool.status = C.PoolStatus.STORED
    _commit(session)

    response = post_form_csrf_mismatch(
        client,
        _path(experiment.id),
        _payload(selected_pool_ids=json.dumps([pool.id])),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")


def test_submit_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    """POST to a non-existent experiment returns 404."""
    response = post_form(
        client,
        _path(999999),
        _payload(),
        token=insider_token,
    )

    assert response.status_code == 404