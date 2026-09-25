"""Lane pooling, flow-cell loading, and read distribution: routing and access.

Each step has a Separate and a Combined action. Legacy Flask used one URL per step
and picked the form from ``experiment.workflow.combined_lanes``; here the templates
pick the action by name, so each variant needs its own path. They used to share one,
which made every Combined action unreachable.

Access matches legacy: insider-only for GET and POST; read distribution on a
non-draft experiment is admin-only.
"""

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C

from ...db.create_units import create_experiment
from .._http import get, post_form

PREFIX = "/htmx/experiments"
COMBINED = C.ExperimentWorkFlow.NOVASEQ_6K_S1_STD
SEPARATE = C.ExperimentWorkFlow.NOVASEQ_6K_S1_XP

# (step path, variant, workflow)
ACTIONS = [
    pytest.param("lane-pools", "combined", COMBINED, id="lane-pools-combined"),
    pytest.param("lane-pools", "separate", SEPARATE, id="lane-pools-separate"),
    pytest.param("load-flow-cell", "combined", COMBINED, id="load-flow-cell-combined"),
    pytest.param("load-flow-cell", "separate", SEPARATE, id="load-flow-cell-separate"),
    pytest.param("distribute-reads", "combined", COMBINED, id="distribute-reads-combined"),
    pytest.param("distribute-reads", "separate", SEPARATE, id="distribute-reads-separate"),
]


def _path(experiment: models.Experiment, step: str, variant: str) -> str:
    return f"{PREFIX}/{experiment.id}/{step}/{variant}"


def _experiment(session: SyncSession, user: models.User, workflow) -> models.Experiment:
    experiment = create_experiment(session, user, workflow)
    session.commit()
    return experiment


@pytest.mark.xfail(
    reason="Templates not yet ported from WTForms (form.csrf_token(), legacy lane_pooling_form/load_flow_cell_form names); Begin returns 500",
    strict=True,
)
@pytest.mark.parametrize("step,variant,workflow", ACTIONS)
def test_begin_renders_the_matching_variant(
    client: TestClient, session: SyncSession, insider, insider_token: str, step: str, variant: str, workflow,
):
    """The form rendered is this variant's, i.e. it posts back to this variant's Submit."""
    experiment = _experiment(session, insider, workflow)
    path = _path(experiment, step, variant)

    response = get(client, path, insider_token)

    assert response.status_code == 200, response.text
    assert f'hx-post="{path}"' in response.text


@pytest.mark.parametrize("step,variant,workflow", ACTIONS)
def test_client_is_denied(
    client: TestClient, session: SyncSession, insider, user_token: str, step: str, variant: str, workflow,
):
    experiment = _experiment(session, insider, workflow)
    path = _path(experiment, step, variant)

    assert get(client, path, user_token).status_code == 403
    assert post_form(client, path, {}, token=user_token).status_code == 403


@pytest.mark.parametrize("step,variant,workflow", ACTIONS)
def test_anonymous_is_redirected_to_login(
    client: TestClient, session: SyncSession, insider, step: str, variant: str, workflow,
):
    experiment = _experiment(session, insider, workflow)
    path = _path(experiment, step, variant)

    for response in (get(client, path), post_form(client, path, {})):
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")


@pytest.mark.parametrize("variant,workflow", [("combined", COMBINED), ("separate", SEPARATE)])
def test_distribute_reads_on_non_draft_experiment_is_admin_only(
    client: TestClient, session: SyncSession, insider, insider_token: str, admin_token: str, variant: str, workflow,
):
    experiment = _experiment(session, insider, workflow)
    experiment.status = C.ExperimentStatus.SEQUENCING
    session.save(experiment)
    session.commit()
    path = _path(experiment, "distribute-reads", variant)

    assert get(client, path, insider_token).status_code == 403
    assert post_form(client, path, {}, token=insider_token).status_code == 403

    # Admin passes the access check. Rendering itself still fails (see xfail above), so use a
    # client that returns the 500 instead of raising it, and only assert on access.
    lenient = TestClient(client.app, raise_server_exceptions=False)
    assert get(lenient, path, admin_token).status_code not in (303, 401, 403)


# ── File browser forms (previously shadowed by the /{subpath:path} catch-all) ──


def test_share_directory_form_renders(client: TestClient, insider_token: str):
    response = get(client, "/htmx/files/share-directory", insider_token, params={"path": "some/dir"})
    assert response.status_code == 200
    assert 'name="recipients"' in response.text


def test_associate_path_form_renders(client: TestClient, insider_token: str):
    response = get(client, "/htmx/files/associate-path", insider_token, params={"path": "some/file.txt"})
    assert response.status_code == 200
    assert 'name="project"' in response.text
