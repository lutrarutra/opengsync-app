"""QubitMeasureWorkflow: record Qubit concentrations of samples, libraries, pools and lanes.

As legacy ``qubit_measure_workflow``: insider-only. Step 1 selects samples, libraries,
pools and/or lanes (at least one); step 2 has one concentration per selected object
(required, ≥ 0) and saves them — a lane's goes to ``original_qubit_concentration`` and an
ACCEPTED pool becomes STORED. Completion redirects to the experiment, the lab prep, or the
dashboard.

Legacy's ``DataRequired`` also rejected 0; zero is a valid measurement here.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import (
    create_experiment, create_lab_prep, create_library, create_pool, create_project, create_sample, create_seq_request,
)
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch


def _url(client: TestClient, route: str) -> str:
    return client.app.url_path_for(f"QubitMeasureWorkflow.{route}")  # type: ignore[attr-defined]


class Objects:
    def __init__(self, session: SyncSession, user: models.User, insider: models.User):
        self.session = session
        seq_request = create_seq_request(session, user)
        self.sample = create_sample(session, user, create_project(session, user))
        self.sample.status = C.SampleStatus.STORED
        self.library = create_library(session, user, seq_request)
        self.library.status = C.LibraryStatus.PREPARING
        self.pool = create_pool(session, user, seq_request)
        self.pool.status = C.PoolStatus.ACCEPTED
        self.experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP)
        session.refresh(self.experiment)
        self.lane = next(lane for lane in self.experiment.lanes if lane.number == 1)  # lanes are created with the experiment
        for obj in (self.sample, self.library, self.pool):
            session.save(obj, flush=True)
        session.commit()
        self.params: dict = {"uuid": str(uuid.uuid4())}

    def selection(self, samples=(), libraries=(), pools=(), lanes=()) -> dict[str, str]:
        return {
            "selected_sample_ids": json.dumps([o.id for o in samples]),
            "selected_library_ids": json.dumps([o.id for o in libraries]),
            "selected_pool_ids": json.dumps([o.id for o in pools]),
            "selected_lane_ids": json.dumps([o.id for o in lanes]),
        }


@pytest.fixture
def objs(session: SyncSession, user, insider) -> Objects:
    return Objects(session, user, insider)


def _select(client: TestClient, objs: Objects, token: str, **selection):
    return post_form(client, _url(client, "SelectSamplesForm.Submit"), objs.selection(**selection), token=token, params=objs.params)


def _measure(client: TestClient, objs: Objects, token: str, values: dict[str, list[tuple[object, str]]]):
    """``values``: form list name (sample_forms, ...) → [(object, concentration)]."""
    data: dict[str, str] = {}
    for list_name, entries in values.items():
        for i, (obj, value) in enumerate(entries):
            data[f"{list_name}-{i}-id_"] = str(obj.id)
            data[f"{list_name}-{i}-name"] = str(getattr(obj, "name", f"Lane {getattr(obj, 'number', '')}"))
            data[f"{list_name}-{i}-qubit_concentration"] = value
    return post_form(client, _url(client, "QubitMeasureForm.Submit"), data, token=token, params=objs.params)


def _reload(session: SyncSession, model, obj_id: int):
    session.expire_all()
    return session.get(model, obj_id)


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_is_denied(client: TestClient, session: SyncSession, objs: Objects, user_token: str):
    assert get(client, _url(client, "Begin"), user_token, params=objs.params).status_code == 403
    assert _select(client, objs, user_token, samples=[objs.sample]).status_code == 403
    assert _measure(client, objs, user_token, {"sample_forms": [(objs.sample, "1.5")]}).status_code == 403
    assert _reload(session, models.Sample, objs.sample.id).qubit_concentration is None


def test_anonymous_is_redirected_to_login(client: TestClient, objs: Objects):
    response = get(client, _url(client, "Begin"), params=objs.params)
    assert response.status_code == 303
    assert "/auth/login" in response.headers.get("location", "")


def test_begin_renders(client: TestClient, objs: Objects, insider_token: str):
    assert get(client, _url(client, "Begin"), insider_token, params=objs.params).status_code == 200


def test_csrf_mismatch_is_rejected(client: TestClient, objs: Objects, insider_token: str):
    response = post_form_csrf_mismatch(client, _url(client, "SelectSamplesForm.Submit"), objs.selection(samples=[objs.sample]), token=insider_token, params=objs.params)
    assert response.status_code != 200


# ── Selection ───────────────────────────────────────────────────────────────


def test_select_one_sample_lists_it_with_current_value(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    objs.sample.qubit_concentration = 3.25
    session.save(objs.sample, flush=True)
    session.commit()

    response = _select(client, objs, insider_token, samples=[objs.sample])

    assert response.status_code == 200, response.text
    assert objs.sample.name in response.text
    assert "3.25" in response.text


def test_select_all_object_types(client: TestClient, objs: Objects, insider_token: str):
    response = _select(client, objs, insider_token, samples=[objs.sample], libraries=[objs.library], pools=[objs.pool], lanes=[objs.lane])

    assert response.status_code == 200, response.text
    for name in (objs.sample.name, objs.library.name, objs.pool.name, f"{objs.experiment.name} - Lane 1"):
        assert name in response.text


def test_empty_selection_is_rejected(client: TestClient, objs: Objects, insider_token: str):
    """Legacy: 'Select at least one sample'."""
    response = _select(client, objs, insider_token)

    assert_form_invalid(response, "Select at least one sample, library, pool or lane.")


def test_unknown_id_is_404(client: TestClient, objs: Objects, insider_token: str):
    response = post_form(
        client, _url(client, "SelectSamplesForm.Submit"),
        {**objs.selection(), "selected_sample_ids": json.dumps([999999])}, token=insider_token, params=objs.params,
    )
    assert response.status_code == 404


# ── Measurements ────────────────────────────────────────────────────────────


def test_measurements_are_saved(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    _select(client, objs, insider_token, samples=[objs.sample], libraries=[objs.library], pools=[objs.pool], lanes=[objs.lane])

    response = _measure(client, objs, insider_token, {
        "sample_forms": [(objs.sample, "1.5")],
        "library_forms": [(objs.library, "2.5")],
        "pool_forms": [(objs.pool, "3.5")],
        "lane_forms": [(objs.lane, "4.5")],
    })

    assert_htmx_redirect(response, "/")
    assert_flash(response, "Changes Saved!", category="success")
    assert _reload(session, models.Sample, objs.sample.id).qubit_concentration == 1.5
    assert _reload(session, models.Library, objs.library.id).qubit_concentration == 2.5
    pool = _reload(session, models.Pool, objs.pool.id)
    assert (pool.qubit_concentration, pool.status) == (3.5, C.PoolStatus.STORED)
    assert _reload(session, models.Lane, objs.lane.id).original_qubit_concentration == 4.5


def test_zero_is_a_valid_measurement(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    _select(client, objs, insider_token, samples=[objs.sample])
    response = _measure(client, objs, insider_token, {"sample_forms": [(objs.sample, "0")]})

    assert response.status_code == 204, response.text
    assert _reload(session, models.Sample, objs.sample.id).qubit_concentration == 0


@pytest.mark.parametrize("value", ["", "-1", "abc"])
def test_missing_negative_or_malformed_concentration_is_rejected(
    client: TestClient, session: SyncSession, objs: Objects, insider_token: str, value: str,
):
    objs.sample.qubit_concentration = 3.0
    session.save(objs.sample, flush=True)
    session.commit()
    _select(client, objs, insider_token, samples=[objs.sample])

    response = _measure(client, objs, insider_token, {"sample_forms": [(objs.sample, value)]})

    assert_form_invalid(response)
    assert _reload(session, models.Sample, objs.sample.id).qubit_concentration == 3.0


def test_redirect_to_experiment(client: TestClient, objs: Objects, insider_token: str):
    objs.params["experiment_id"] = objs.experiment.id
    _select(client, objs, insider_token, lanes=[objs.lane])

    response = _measure(client, objs, insider_token, {"lane_forms": [(objs.lane, "1.0")]})

    assert_htmx_redirect(response, f"/experiments/{objs.experiment.id}")


def test_redirect_to_lab_prep(client: TestClient, session: SyncSession, objs: Objects, insider, insider_token: str):
    lab_prep = create_lab_prep(session, insider)
    objs.library.lab_prep_id = lab_prep.id
    session.save(objs.library, flush=True)
    session.commit()
    objs.params["lab_prep_id"] = lab_prep.id
    _select(client, objs, insider_token, libraries=[objs.library])

    response = _measure(client, objs, insider_token, {"library_forms": [(objs.library, "1.0")]})

    assert_htmx_redirect(response, f"/lab_preps/{lab_prep.id}")


# ── Navigation and state ────────────────────────────────────────────────────


def test_back_to_selection(client: TestClient, objs: Objects, insider_token: str):
    _select(client, objs, insider_token, samples=[objs.sample])

    response = get(client, _url(client, "SelectSamplesForm.Previous"), insider_token, params=objs.params)
    assert response.status_code == 200, response.text


def test_completion_clears_state(client: TestClient, objs: Objects, insider_token: str):
    _select(client, objs, insider_token, samples=[objs.sample])
    _measure(client, objs, insider_token, {"sample_forms": [(objs.sample, "1.0")]})

    r = Redis(connection_pool=client.app.state.redis_pool)  # type: ignore[attr-defined]
    assert list(r.scan_iter(f"QubitMeasureWorkflow:{objs.params['uuid']}:*")) == []


def test_measure_step_without_selection_is_400(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    """Step 2 without a run that went through selection (expired, replayed) is a controlled 400."""
    response = _measure(client, objs, insider_token, {"sample_forms": [(objs.sample, "1.0")]})

    assert response.status_code == 400
    assert _reload(session, models.Sample, objs.sample.id).qubit_concentration is None


def test_only_selected_objects_are_updated(client: TestClient, session: SyncSession, objs: Objects, user, insider_token: str):
    """Rows of step 2 are submitted by the client: an object that was not selected must not be changed."""
    other = create_sample(session, user, create_project(session, user))
    session.commit()
    _select(client, objs, insider_token, samples=[objs.sample])

    response = _measure(client, objs, insider_token, {"sample_forms": [(objs.sample, "1.0"), (other, "9.0")]})

    assert response.status_code == 400
    assert _reload(session, models.Sample, other.id).qubit_concentration is None
    assert _reload(session, models.Sample, objs.sample.id).qubit_concentration is None
