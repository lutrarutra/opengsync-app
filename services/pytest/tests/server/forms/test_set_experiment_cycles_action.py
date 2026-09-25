"""SetExperimentCyclesAction: render, permissions, and cycle updates.

Access control:
- **GET (Begin)** has no auth gate — any authenticated user can view.
- **POST (Submit)** requires ``require_insider`` — only staff can save changes.
"""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_experiment
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
    return f"{PREFIX}/{experiment_id}/cycles"


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "cycles_r1": "100",
        "cycles_r2": "100",
        "cycles_i1": "10",
        "cycles_i2": "10",
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _commit(session: SyncSession) -> None:
    session.commit()


def _reload(session: SyncSession, experiment: models.Experiment) -> models.Experiment:
    session.expire_all()
    return session.get_one(Q.experiment.select(id=experiment.id))


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_get_allows_any_user(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """GET has no auth gate — a regular CLIENT user can view the form."""
    experiment = create_experiment(session, user, WORKFLOW)
    _commit(session)

    response = get(client, _path(experiment.id), user_token)

    assert response.status_code == 200
    assert 'name="cycles_r1"' in response.text
    assert 'name="cycles_r2"' in response.text
    assert 'name="cycles_i1"' in response.text
    assert 'name="cycles_i2"' in response.text
    assert 'name="csrf_token"' in response.text


def test_render_get_unknown_is_404(
    client: TestClient,
    user_token: str,
):
    assert get(client, _path(999999), user_token).status_code == 404


def test_render_get_prefills_cycles(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """The GET handler pre-fills cycle fields from the experiment values."""
    experiment = create_experiment(session, user, WORKFLOW)
    # create_experiment defaults to 1 for all cycle fields
    _commit(session)

    response = get(client, _path(experiment.id), user_token)

    assert response.status_code == 200
    assert 'value="1"' in response.text or 'value="1"' in response.text


# ── Submit (POST) ────────────────────────────────────────────────────────────


def test_submit_requires_insider(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    """A CLIENT user is denied on POST even with valid payload."""
    experiment = create_experiment(session, user, WORKFLOW)
    _commit(session)

    response = post_form(
        client,
        _path(experiment.id),
        _payload(),
        token=user_token,
    )

    assert response.status_code == 403


def test_submit_updates_cycles(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """A valid POST by an insider persists all four cycle values."""
    experiment = create_experiment(session, user, WORKFLOW)
    _commit(session)

    response = post_form(
        client,
        _path(experiment.id),
        _payload(
            cycles_r1="151",
            cycles_r2="151",
            cycles_i1="8",
            cycles_i2="8",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert "tab=checklist-tab" in response.headers.get("HX-Redirect", "")
    assert_flash(response, "Changes Saved!", category="success")

    updated = _reload(session, experiment)
    assert updated.r1_cycles == 151
    assert updated.r2_cycles == 151
    assert updated.i1_cycles == 8
    assert updated.i2_cycles == 8


def test_submit_empty_cycles(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """Sending empty strings should save all fields as None (optional fields)."""
    experiment = create_experiment(session, user, WORKFLOW)
    # Defaults are 1; after empty submission they should become None
    _commit(session)

    response = post_form(
        client,
        _path(experiment.id),
        _payload(
            cycles_r1="",
            cycles_r2="",
            cycles_i1="",
            cycles_i2="",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert "tab=checklist-tab" in response.headers.get("HX-Redirect", "")
    assert_flash(response, "Changes Saved!", category="success")

    updated = _reload(session, experiment)
    assert updated.r1_cycles is None
    assert updated.r2_cycles is None
    assert updated.i1_cycles is None
    assert updated.i2_cycles is None


def test_submit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    user,
    insider,
    insider_token: str,
):
    """A CSRF mismatch re-renders the form with an error flash."""
    experiment = create_experiment(session, user, WORKFLOW)
    _commit(session)

    response = post_form_csrf_mismatch(
        client,
        _path(experiment.id),
        _payload(),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")

    # Experiment should be unchanged
    updated = _reload(session, experiment)
    assert updated.r1_cycles == 1
    assert updated.r2_cycles == 1
    assert updated.i1_cycles == 1
    assert updated.i2_cycles == 1


def test_submit_unknown_is_404(
    client: TestClient,
    insider_token: str,
):
    response = post_form(
        client,
        _path(999999),
        _payload(),
        token=insider_token,
    )

    assert response.status_code == 404