"""LaneQCWorkflow: phi-X, average library size and qubit concentration per lane.

As legacy ``lane_qc_workflow``: insider-only, single step. Experiments with combined lanes
get one set of values that is applied to every lane (``UnifiedQCLanesForm``); the others get
one row per lane (``QCLanesForm``). Values are prefilled from the lanes (the sequencing qubit
concentration, falling back to the original one). Completion redirects to the experiment.

Basic separate-lane submit, access and fragment size 0 are in ``tests/server/test_workflows.py``.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_experiment
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

COMBINED = C.ExperimentWorkFlow.NOVASEQ_6K_SP_STD
SEPARATE = C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP
VALUES = {"phi_x": "1.5", "avg_fragment_size": "350", "qubit_concentration": "2.5"}


def _url(client: TestClient, route: str) -> str:
    return client.app.url_path_for(f"LaneQCWorkflow.{route}")  # type: ignore[attr-defined]


def _experiment(session: SyncSession, insider: models.User, workflow: C.ExperimentWorkFlow) -> models.Experiment:
    experiment = create_experiment(session, insider, workflow)
    session.commit()
    return experiment


def _lanes(session: SyncSession, experiment: models.Experiment) -> list[models.Lane]:
    session.expire_all()
    return sorted(session.get_all(Q.lane.select(experiment_id=experiment.id), limit=None), key=lambda lane: lane.number)


def _qc(lane: models.Lane) -> tuple:
    return (lane.phi_x, lane.avg_fragment_size, lane.original_qubit_concentration)


def _params(experiment: models.Experiment) -> dict:
    return {"experiment_id": experiment.id, "uuid": str(uuid.uuid4())}


def _begin(client: TestClient, token: str, params: dict):
    return get(client, _url(client, "Begin"), token, params=params)


def _separate_payload(lanes: list[models.Lane], **overrides: dict[str, str]) -> dict[str, str]:
    """One row per lane with VALUES; ``overrides`` maps 'i' (row index as str) to changed fields."""
    payload = {}
    for i, lane in enumerate(lanes):
        row = {"lane_id": str(lane.id), **VALUES, **overrides.get(str(i), {})}
        payload.update({f"fields-{i}-{key}": value for key, value in row.items() if value is not None})
    return payload


def _submit_separate(client: TestClient, token: str, params: dict, payload: dict):
    return post_form(client, _url(client, "QCLanesForm.Submit"), payload, token=token, params=params)


def _submit_combined(client: TestClient, token: str, params: dict, **overrides: str | None):
    payload = {key: value for key, value in {**VALUES, **overrides}.items() if value is not None}
    return post_form(client, _url(client, "UnifiedQCLanesForm.Submit"), payload, token=token, params=params)


# ── Combined lanes ──────────────────────────────────────────────────────────


def test_combined_begin_renders_one_set_of_values_prefilled_from_the_first_lane(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    experiment = _experiment(session, insider, COMBINED)
    for lane in _lanes(session, experiment):
        lane.phi_x, lane.avg_fragment_size = 2.25, 410
        lane.original_qubit_concentration, lane.sequencing_qubit_concentration = 1.0, 3.75
        session.save(lane, flush=True)
    session.commit()

    response = _begin(client, insider_token, _params(experiment))

    assert response.status_code == 200, response.text
    assert "fields-0-phi_x" not in response.text
    for name, value in (("phi_x", "2.25"), ("avg_fragment_size", "410"), ("qubit_concentration", "3.75")):
        assert f'name="{name}"' in response.text
        assert f'value="{value}"' in response.text


def test_combined_submit_sets_every_lane_and_clears_state(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    experiment = _experiment(session, insider, COMBINED)
    assert len(_lanes(session, experiment)) > 1
    params = _params(experiment)
    _begin(client, insider_token, params)

    response = _submit_combined(client, insider_token, params)

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert_flash(response, "Saved!", "success")
    assert {_qc(lane) for lane in _lanes(session, experiment)} == {(1.5, 350, 2.5)}
    assert Redis(connection_pool=client.app.state.redis_pool).keys(f"LaneQCWorkflow:{params['uuid']}:*") == []  # type: ignore[attr-defined]


@pytest.mark.parametrize("overrides", [
    {"phi_x": None},
    {"avg_fragment_size": None},
    {"qubit_concentration": None},
    {"phi_x": "-0.5"},
    {"qubit_concentration": "-1"},
    {"avg_fragment_size": "0"},
    {"avg_fragment_size": "-300"},
    {"avg_fragment_size": "350.5"},
    {"phi_x": "abc"},
], ids=lambda o: "-".join(f"{k}={v}" for k, v in o.items()))
def test_combined_invalid_values_are_rejected(
    client: TestClient, session: SyncSession, insider, insider_token: str, overrides: dict,
):
    experiment = _experiment(session, insider, COMBINED)
    params = _params(experiment)

    response = _submit_combined(client, insider_token, params, **overrides)

    assert_form_invalid(response)
    assert {_qc(lane) for lane in _lanes(session, experiment)} == {(None, None, None)}


def test_combined_zero_phi_x_and_qubit_are_accepted(client: TestClient, session: SyncSession, insider, insider_token: str):
    """Only the fragment size must be positive (molarity divides by it); 0 % phi-X is a valid value."""
    experiment = _experiment(session, insider, COMBINED)

    response = _submit_combined(client, insider_token, _params(experiment), phi_x="0", qubit_concentration="0")

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert {_qc(lane) for lane in _lanes(session, experiment)} == {(0.0, 350, 0.0)}


# ── Separate lanes ──────────────────────────────────────────────────────────


def test_separate_begin_prefills_each_lane(client: TestClient, session: SyncSession, insider, insider_token: str):
    experiment = _experiment(session, insider, SEPARATE)
    first, second = _lanes(session, experiment)[:2]
    first.phi_x, first.avg_fragment_size, first.original_qubit_concentration = 1.25, 300, 2.0
    second.original_qubit_concentration, second.sequencing_qubit_concentration = 1.0, 4.5
    session.save(first, flush=True)
    session.save(second, flush=True)
    session.commit()

    response = _begin(client, insider_token, _params(experiment))

    assert response.status_code == 200, response.text
    text = response.text
    assert 'name="fields-0-lane_id"' in text and 'name="fields-1-lane_id"' in text
    assert 'value="1.25"' in text and 'value="300"' in text and 'value="2.0"' in text
    assert 'value="4.5"' in text  # sequencing qubit preferred over the original one


def test_separate_lanes_get_their_own_values(client: TestClient, session: SyncSession, insider, insider_token: str):
    experiment = _experiment(session, insider, SEPARATE)
    lanes = _lanes(session, experiment)
    params = _params(experiment)
    _begin(client, insider_token, params)

    response = _submit_separate(client, insider_token, params, _separate_payload(
        lanes, **{"1": {"phi_x": "0.5", "avg_fragment_size": "500", "qubit_concentration": "4"}},
    ))

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    first, second = _lanes(session, experiment)[:2]
    assert _qc(first) == (1.5, 350, 2.5)
    assert _qc(second) == (0.5, 500, 4.0)


@pytest.mark.parametrize("overrides", [
    {"phi_x": None},
    {"avg_fragment_size": None},
    {"qubit_concentration": None},
    {"phi_x": "-0.5"},
    {"qubit_concentration": "-1"},
    {"avg_fragment_size": "-300"},
    {"qubit_concentration": "abc"},
], ids=lambda o: "-".join(f"{k}={v}" for k, v in o.items()))
def test_separate_invalid_value_in_one_lane_saves_nothing(
    client: TestClient, session: SyncSession, insider, insider_token: str, overrides: dict,
):
    experiment = _experiment(session, insider, SEPARATE)
    lanes = _lanes(session, experiment)

    response = _submit_separate(client, insider_token, _params(experiment), _separate_payload(lanes, **{"1": overrides}))

    assert_form_invalid(response)
    assert {_qc(lane) for lane in _lanes(session, experiment)} == {(None, None, None)}


def test_separate_lane_left_out_is_unchanged(client: TestClient, session: SyncSession, insider, insider_token: str):
    experiment = _experiment(session, insider, SEPARATE)
    lanes = _lanes(session, experiment)

    response = _submit_separate(client, insider_token, _params(experiment), _separate_payload(lanes[:1]))

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    first, second = _lanes(session, experiment)[:2]
    assert _qc(first) == (1.5, 350, 2.5)
    assert _qc(second) == (None, None, None)


def test_separate_duplicate_lane_takes_the_last_row(client: TestClient, session: SyncSession, insider, insider_token: str):
    """As legacy: rows are applied in order, so a lane given twice keeps the last values."""
    experiment = _experiment(session, insider, SEPARATE)
    first = _lanes(session, experiment)[0]

    response = _submit_separate(client, insider_token, _params(experiment), _separate_payload(
        [first, first], **{"1": {"phi_x": "9"}},
    ))

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert _qc(_lanes(session, experiment)[0]) == (9.0, 350, 2.5)


def test_separate_unknown_lane_is_404_and_rolls_back_earlier_lanes(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    experiment = _experiment(session, insider, SEPARATE)
    lanes = _lanes(session, experiment)
    payload = _separate_payload(lanes)
    payload["fields-1-lane_id"] = "999999"

    response = _submit_separate(client, insider_token, _params(experiment), payload)

    assert response.status_code == 404
    assert {_qc(lane) for lane in _lanes(session, experiment)} == {(None, None, None)}


def test_separate_lane_of_another_experiment_is_rejected(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    experiment = _experiment(session, insider, SEPARATE)
    other = _experiment(session, insider, SEPARATE)
    lanes = _lanes(session, experiment)
    foreign = _lanes(session, other)[0]

    response = _submit_separate(client, insider_token, _params(experiment), _separate_payload([lanes[0], foreign]))

    assert response.status_code == 404
    assert {_qc(lane) for lane in _lanes(session, experiment) + _lanes(session, other)} == {(None, None, None)}


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_cannot_submit_combined(client: TestClient, session: SyncSession, insider, user_token: str):
    experiment = _experiment(session, insider, COMBINED)

    assert _begin(client, user_token, _params(experiment)).status_code == 403
    assert _submit_combined(client, user_token, _params(experiment)).status_code == 403
    assert {_qc(lane) for lane in _lanes(session, experiment)} == {(None, None, None)}


def test_unknown_experiment_is_404(client: TestClient, insider_token: str):
    assert _begin(client, insider_token, {"experiment_id": 999999}).status_code == 404


def test_anonymous_is_redirected_to_login(client: TestClient, session: SyncSession, insider):
    experiment = _experiment(session, insider, COMBINED)
    assert _begin(client, None, _params(experiment)).status_code == 303


def test_csrf_mismatch_changes_nothing(client: TestClient, session: SyncSession, insider, insider_token: str):
    experiment = _experiment(session, insider, COMBINED)

    response = post_form_csrf_mismatch(client, _url(client, "UnifiedQCLanesForm.Submit"), VALUES, token=insider_token, params=_params(experiment))

    assert_form_invalid(response)
    assert {_qc(lane) for lane in _lanes(session, experiment)} == {(None, None, None)}
