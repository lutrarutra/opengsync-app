"""GenerateSequencerLoadingChecklistAction: fill the workflow's markdown template.

Only NovaSeq X workflows have a template (``static/resources/templates/seq_loading``).
``novaseq_x.md`` declares four parameters: ``naoh`` (8.5), ``preload`` (127.5),
``pool_volume`` (34) and the per-lane list ``phi_x`` (no default), so a 2-lane 1.5B
flow cell renders five inputs. Submitting writes a ``SEQUENCER_LOADING_CHECKLIST``
media file for the experiment.

The lane table has one row per lane; lanes loaded with the identical set of pools are
merged into one row ("1,2") whose volumes scale with the number of lanes and whose PhiX
is summed over them. Legacy ``sequencer_loading_checklist`` was insider-only.
"""

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import config

from ...db.create_units import create_experiment, create_pool, create_seq_request
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

PREFIX = "/htmx/experiments"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"
WORKFLOW = C.ExperimentWorkFlow.NOVASEQ_X_1B_XP  # 2 lanes, novaseq_x.md


def _path(experiment_id: int) -> str:
    return f"{PREFIX}/{experiment_id}/sequencer-loading-checklist"


PARAMS = [
    ("NaOH", "naoh"),
    ("Preload", "preload"),
    ("Pool Volume", "pool_volume"),
    ("Phi X (Lane 1)", "phi_x_lane_1"),
    ("Phi X (Lane 2)", "phi_x_lane_2"),
]


def _payload(**values: object) -> dict[str, str]:
    defaults = {"naoh": 8.5, "preload": 127.5, "pool_volume": 34, "phi_x_lane_1": 2, "phi_x_lane_2": 3}
    defaults.update(values)
    data: dict[str, str] = {}
    for i, (label, var_name) in enumerate(PARAMS):
        data[f"parameters-{i}-param_label"] = label
        data[f"parameters-{i}-param_value"] = "" if defaults[var_name] is None else str(defaults[var_name])
        data[f"parameters-{i}-var_name"] = var_name
    return data


def _checklists(session: SyncSession, experiment: models.Experiment) -> list[models.MediaFile]:
    session.expire_all()
    return list(session.get_all(
        sa.select(models.MediaFile).where(
            models.MediaFile.experiment_id == experiment.id,
            models.MediaFile.type == C.MediaFileType.SEQUENCER_LOADING_CHECKLIST,
        ),
        limit=None,
    ))


def _content(file: models.MediaFile) -> str:
    path = Path(config.settings.app_config.media_folder) / C.MediaFileType.SEQUENCER_LOADING_CHECKLIST.dir / f"{file.uuid}.md"
    return path.read_text()


def _lanes(session: SyncSession, experiment: models.Experiment) -> list[models.Lane]:
    return sorted(session.get_all(Q.lane.select(experiment_id=experiment.id), limit=None), key=lambda lane: lane.number)


def _load(session: SyncSession, experiment: models.Experiment, lane: models.Lane, pool: models.Pool) -> None:
    session.add(models.links.LanePoolLink(
        lane_id=lane.id, pool_id=pool.id, experiment_id=experiment.id, lane_num=lane.number,
    ))


@pytest.fixture
def experiment(session: SyncSession, user, insider) -> models.Experiment:
    """Pool_A on lane 1, Pool_B on lane 2."""
    experiment = create_experiment(session, insider, WORKFLOW)
    experiment.name = "EXP_X"
    session.flush()
    lane_1, lane_2 = _lanes(session, experiment)
    seq_request = create_seq_request(session, user)
    pool_a = create_pool(session, user, seq_request)
    pool_a.name = "Pool_A"
    pool_b = create_pool(session, user, seq_request)
    pool_b.name = "Pool_B"
    session.flush()
    _load(session, experiment, lane_1, pool_a)
    _load(session, experiment, lane_2, pool_b)
    session.commit()
    return experiment


def _row(*cells: str) -> str:
    return "\n      ".join(f"<td>{cell}</td>" for cell in cells)


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_lists_parameters_with_defaults(client: TestClient, experiment, insider_token: str):
    response = get(client, _path(experiment.id), insider_token)

    assert response.status_code == 200
    for i, (label, var_name) in enumerate(PARAMS):
        assert label in response.text
        assert f'name="parameters-{i}-param_value"' in response.text
        assert var_name in response.text
    assert 'name="parameters-5-param_value"' not in response.text
    for default in ("8.5", "127.5", "34"):
        assert f'value="{default}' in response.text


def test_render_one_phi_x_input_per_lane(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_X_10B_XP)  # 8 lanes
    session.commit()

    response = get(client, _path(experiment.id), insider_token)

    assert response.status_code == 200
    for lane in range(1, 9):
        assert f"Phi X (Lane {lane})" in response.text
    assert "Phi X (Lane 9)" not in response.text


def test_render_denies_client(client: TestClient, experiment, user_token: str):
    assert get(client, _path(experiment.id), user_token).status_code == 403


def test_render_unknown_experiment_is_404(client: TestClient, insider_token: str):
    assert get(client, _path(999999), insider_token).status_code == 404


def test_render_workflow_without_template_is_controlled(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    """NovaSeq 6000 workflows have no template: the error page names the reason.

    The checklist only offers the button when the workflow has a template; legacy raised
    ``ValueError`` (500) here too.
    """
    experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_S4_STD)
    session.commit()

    lenient = TestClient(client.app, raise_server_exceptions=False)
    response = get(lenient, _path(experiment.id), insider_token)

    assert response.status_code == 500
    assert "does not have a sequencer loading checklist template" in response.text


def test_render_does_not_create_a_file(
    client: TestClient, session: SyncSession, experiment, insider_token: str,
):
    assert get(client, _path(experiment.id), insider_token).status_code == 200
    assert _checklists(session, experiment) == []


# ── Submit (POST) ───────────────────────────────────────────────────────────


def test_submit_writes_checklist_file(
    client: TestClient, session: SyncSession, experiment, insider, insider_token: str,
):
    response = post_form(client, _path(experiment.id), _payload(), token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert "tab=checklist-tab" in response.headers["HX-Redirect"]
    assert_flash(response, "Checklist Generated!", category="success")

    files = _checklists(session, experiment)
    assert len(files) == 1
    file = files[0]
    assert file.name == "sequencer_loading_checklist"
    assert file.extension == ".md"
    assert file.uploader_id == insider.id
    content = _content(file)
    assert file.size_bytes == len(content.encode("utf-8"))

    assert content.startswith("# Experiment EXP_X\n")
    assert f"- Workflow: {WORKFLOW.display_name}" in content
    assert f"- Operator: {insider.name}" in content
    assert "- `NaOH`: 8.5" in content
    assert "- `Phi X (Lane 2)`: 3.0" in content
    # Template body rendered, parameter block stripped, placeholders filled.
    assert "## 1. Prepare NovaSeq X" in content
    assert "## 0. Parameters" not in content
    assert "{{" not in content


def test_submit_one_row_per_lane(
    client: TestClient, session: SyncSession, experiment, insider_token: str,
):
    post_form(client, _path(experiment.id), _payload(), token=insider_token)
    content = _content(_checklists(session, experiment)[0])

    # Lane, Pool, Pool [µL], NaOH [µL], PhiX [µL]
    assert _row("1", "Pool_A", "34.0", "8.5", "2.0") in content
    assert _row("2", "Pool_B", "34.0", "8.5", "3.0") in content
    # Lane, Pool, Pre-load Buffer [µL]
    assert _row("1", "Pool_A", "127.5") in content


def test_submit_lanes_with_the_same_pools_are_merged(
    client: TestClient, session: SyncSession, user, insider, insider_token: str,
):
    """A pool alone on both lanes gives one row with 2× volumes and the summed PhiX."""
    experiment = create_experiment(session, insider, WORKFLOW)
    session.flush()
    pool = create_pool(session, user, create_seq_request(session, user))
    pool.name = "Pool_C"
    session.flush()
    for lane in _lanes(session, experiment):
        _load(session, experiment, lane, pool)
    session.commit()

    post_form(client, _path(experiment.id), _payload(), token=insider_token)
    content = _content(_checklists(session, experiment)[0])

    assert _row("1,2", "Pool_C", "68.0", "17.0", "5.0") in content
    assert _row("1,2", "Pool_C", "255.0") in content


def test_submit_pools_sharing_a_lane_are_grouped(
    client: TestClient, session: SyncSession, user, insider, insider_token: str,
):
    """Two pools on the same single lane share one row ("Pool_A;Pool_B")."""
    experiment = create_experiment(session, insider, WORKFLOW)
    session.flush()
    lane_1, _ = _lanes(session, experiment)
    seq_request = create_seq_request(session, user)
    for name in ("Pool_B", "Pool_A"):
        pool = create_pool(session, user, seq_request)
        pool.name = name
        session.flush()
        _load(session, experiment, lane_1, pool)
    session.commit()

    post_form(client, _path(experiment.id), _payload(), token=insider_token)
    content = _content(_checklists(session, experiment)[0])

    assert "<td>Pool_A;Pool_B</td>" in content


def test_submit_zero_values_are_blank(
    client: TestClient, session: SyncSession, experiment, insider_token: str,
):
    """Zero cells are rendered empty (``replace({0.0: ""})``)."""
    post_form(client, _path(experiment.id), _payload(phi_x_lane_1=0, phi_x_lane_2=0), token=insider_token)
    content = _content(_checklists(session, experiment)[0])

    assert _row("1", "Pool_A", "34.0", "8.5", "") in content


def test_submit_experiment_without_pools(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    experiment = create_experiment(session, insider, WORKFLOW)
    session.commit()

    response = post_form(client, _path(experiment.id), _payload(), token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert len(_checklists(session, experiment)) == 1


def test_submit_twice_creates_two_files(
    client: TestClient, session: SyncSession, experiment, insider_token: str,
):
    for _ in range(2):
        assert_htmx_redirect(post_form(client, _path(experiment.id), _payload(), token=insider_token))

    files = _checklists(session, experiment)
    assert len(files) == 2
    assert files[0].uuid != files[1].uuid


def test_submit_missing_value_is_rejected(
    client: TestClient, session: SyncSession, experiment, insider_token: str,
):
    response = post_form(client, _path(experiment.id), _payload(naoh=None), token=insider_token)

    assert_form_invalid(response)
    assert _checklists(session, experiment) == []


def test_submit_non_numeric_value_is_rejected(
    client: TestClient, session: SyncSession, experiment, insider_token: str,
):
    response = post_form(client, _path(experiment.id), _payload(pool_volume="lots"), token=insider_token)

    assert_form_invalid(response)
    assert _checklists(session, experiment) == []


def test_submit_without_parameters_is_rejected(
    client: TestClient, session: SyncSession, experiment, insider_token: str,
):
    response = post_form(client, _path(experiment.id), {}, token=insider_token)

    assert_form_invalid(response)
    assert _checklists(session, experiment) == []


def test_submit_denies_client(
    client: TestClient, session: SyncSession, experiment, user_token: str,
):
    response = post_form(client, _path(experiment.id), _payload(), token=user_token)

    assert response.status_code == 403
    assert _checklists(session, experiment) == []


def test_submit_unknown_experiment_is_404(client: TestClient, insider_token: str):
    assert post_form(client, _path(999999), _payload(), token=insider_token).status_code == 404


def test_submit_csrf_mismatch_creates_nothing(
    client: TestClient, session: SyncSession, experiment, insider_token: str,
):
    response = post_form_csrf_mismatch(client, _path(experiment.id), _payload(), token=insider_token)

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert _checklists(session, experiment) == []
