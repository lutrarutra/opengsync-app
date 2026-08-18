"""LaneQCWorkflow: insider gate, uuid, SubFormList POST, Redis wiped on complete."""

import uuid

from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, queries as Q, categories as C

from ..db.create_units import create_experiment
from ._http import get, post_form

# QCLanesForm → _class_name_to_path → /q-c-lanes (consecutive capitals split).
QC_LANES_PATH = "/htmx/workflows/lane-qc/q-c-lanes"


def _commit(session: SyncSession) -> None:
    session.commit()


def _qc_payload(lanes) -> dict[str, str]:
    data: dict[str, str] = {}
    for i, lane in enumerate(lanes):
        data[f"fields-{i}-lane_id"] = str(lane.id)
        data[f"fields-{i}-phi_x"] = "1.5"
        data[f"fields-{i}-avg_fragment_size"] = "350"
        data[f"fields-{i}-qubit_concentration"] = "2.5"
    return data


def test_lane_qc_begin_requires_insider(
    client: TestClient, session: SyncSession, user, user_token, insider, insider_token,
):
    experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP)
    _commit(session)

    denied = get(
        client, "/htmx/workflows/lane-qc/begin", user_token,
        params={"experiment_id": experiment.id},
    )
    assert denied.status_code == 403

    allowed = get(
        client, "/htmx/workflows/lane-qc/begin", insider_token,
        params={"experiment_id": experiment.id},
    )
    assert allowed.status_code not in (303, 401, 403)


def test_lane_qc_submit_updates_lanes_and_clears_redis(
    client: TestClient, session: SyncSession, insider, insider_token,
):
    experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP)
    _commit(session)
    lanes = session.get_all(Q.lane.select(experiment_id=experiment.id), limit=None)
    assert len(lanes) >= 1

    wf_uuid = str(uuid.uuid4())
    begun = get(
        client, "/htmx/workflows/lane-qc/begin", insider_token,
        params={"experiment_id": experiment.id, "uuid": wf_uuid},
    )
    assert begun.status_code not in (303, 401, 403)

    response = post_form(
        client,
        QC_LANES_PATH,
        _qc_payload(lanes),
        token=insider_token,
        params={"experiment_id": experiment.id, "uuid": wf_uuid},
    )
    assert response.status_code == 204
    assert "HX-Redirect" in response.headers

    session.expire_all()
    updated = session.get_all(Q.lane.select(experiment_id=experiment.id), limit=None)
    for lane in updated:
        assert lane.phi_x == 1.5
        assert lane.avg_fragment_size == 350
        assert lane.original_qubit_concentration == 2.5

    leftover = Redis(connection_pool=client.app.state.redis_pool).keys(f"LaneQCWorkflow:{wf_uuid}:*")
    assert leftover == []


def test_lane_qc_client_cannot_submit(
    client: TestClient, session: SyncSession, user, user_token, insider,
):
    experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP)
    _commit(session)
    lanes = session.get_all(Q.lane.select(experiment_id=experiment.id), limit=None)

    response = post_form(
        client,
        QC_LANES_PATH,
        _qc_payload(lanes),
        token=user_token,
        params={"experiment_id": experiment.id, "uuid": str(uuid.uuid4())},
    )
    assert response.status_code == 403
