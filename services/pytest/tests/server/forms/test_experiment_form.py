"""ExperimentForm: create/edit, insider gating, lane setup, and field validation."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_experiment, create_sequencer
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

CREATE = "/htmx/experiments/create"
EDIT = "/htmx/experiments/{experiment_id}/edit"
WORKFLOW = C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _edit_path(experiment_id: int) -> str:
    return EDIT.format(experiment_id=experiment_id)


def _payload(name: str, sequencer_id: int, operator_id: int, **overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "name": name,
        "workflow": str(WORKFLOW.id),
        "sequencer": str(sequencer_id),
        "operator": str(operator_id),
        "status": str(C.ExperimentStatus.DRAFT.id),
        "r1_cycles": "151",
        "i1_cycles": "8",
        "i2_cycles": "8",
        "r2_cycles": "151",
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _experiment(session: SyncSession, name: str) -> models.Experiment | None:
    session.expire_all()
    return session.first(Q.experiment.select(name=name))


def _reload(session: SyncSession, experiment: models.Experiment) -> models.Experiment:
    session.expire_all()
    return session.get_one(Q.experiment.select(id=experiment.id))


def _lanes(session: SyncSession, experiment_id: int) -> list[models.Lane]:
    session.expire_all()
    return session.get_all(Q.lane.select(experiment_id=experiment_id), limit=None)


def test_experiment_form_route_shape():
    from server.forms.models.ExperimentForm import ExperimentForm

    assert {(route.method, route.name) for route in ExperimentForm._routes} == {
        ("GET", "ExperimentForm.Create"),
        ("POST", "ExperimentForm.Create"),
        ("GET", "ExperimentForm.Edit"),
        ("POST", "ExperimentForm.Edit"),
    }


def test_create_form_get_prefills_operator(
    client: TestClient,
    insider,
    insider_token: str,
):
    response = get(client, CREATE, insider_token)

    assert response.status_code == 200
    assert 'name="name"' in response.text
    assert 'name="workflow"' in response.text
    assert 'name="sequencer"' in response.text
    assert f'value="{insider.id}"' in response.text


def test_create_form_get_denied_for_client(client: TestClient, user_token: str):
    assert get(client, CREATE, user_token).status_code == 403


def test_edit_form_get_renders_experiment(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    experiment = create_experiment(session, insider, WORKFLOW)
    session.commit()

    response = get(client, _edit_path(experiment.id), insider_token)

    assert response.status_code == 200
    assert experiment.name in response.text


def test_edit_form_get_unknown_experiment_is_404(client: TestClient, insider_token: str):
    assert get(client, _edit_path(999999), insider_token).status_code == 404


def test_edit_form_get_denied_for_client(
    client: TestClient,
    session: SyncSession,
    insider,
    user_token: str,
):
    experiment = create_experiment(session, insider, WORKFLOW)
    session.commit()

    assert get(client, _edit_path(experiment.id), user_token).status_code == 403


def test_create_persists_experiment_and_lanes(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    sequencer = create_sequencer(session)
    session.commit()
    name = "EXP_CREATE_001"

    response = post_form(
        client,
        CREATE,
        _payload(name, sequencer.id, insider.id),
        token=insider_token,
    )

    assert_htmx_redirect(response, "/experiments/")
    assert_flash(response, "Experiment Created!", category="success")

    experiment = _experiment(session, name)
    assert experiment is not None
    assert experiment.workflow == WORKFLOW
    assert experiment.status == C.ExperimentStatus.DRAFT
    assert experiment.sequencer_id == sequencer.id
    assert experiment.operator_id == insider.id
    assert experiment.r1_cycles == 151
    assert experiment.r2_cycles == 151
    assert experiment.i1_cycles == 8
    assert experiment.i2_cycles == 8
    assert len(_lanes(session, experiment.id)) == WORKFLOW.flow_cell_type.num_lanes


def test_create_duplicate_name_rerenders(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    existing = create_experiment(session, insider, WORKFLOW)
    sequencer = create_sequencer(session)
    session.commit()

    response = post_form(
        client,
        CREATE,
        _payload(existing.name, sequencer.id, insider.id),
        token=insider_token,
    )

    assert_form_invalid(response, "An experiment with this name already exists.")
    assert session.count(Q.experiment.select(name=existing.name)) == 1


def test_create_requires_name(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    sequencer = create_sequencer(session)
    session.commit()
    before = session.count(Q.experiment.select())

    payload = _payload("placeholder", sequencer.id, insider.id)
    payload["name"] = ""
    response = post_form(client, CREATE, payload, token=insider_token)

    assert_form_invalid(response)
    assert "Experiment Name is required" in response.text
    assert session.count(Q.experiment.select()) == before


def test_create_name_max_length(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    sequencer = create_sequencer(session)
    session.commit()
    name = "x" * (models.Experiment.name.type.length + 1)

    response = post_form(
        client,
        CREATE,
        _payload(name, sequencer.id, insider.id),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "at most" in response.text
    assert _experiment(session, name) is None


def test_create_invalid_workflow_rerenders(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    sequencer = create_sequencer(session)
    session.commit()

    response = post_form(
        client,
        CREATE,
        _payload("EXP_BAD_WORKFLOW", sequencer.id, insider.id, workflow=999),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert _experiment(session, "EXP_BAD_WORKFLOW") is None


def test_create_non_integer_cycles_rerenders(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    sequencer = create_sequencer(session)
    session.commit()

    response = post_form(
        client,
        CREATE,
        _payload("EXP_BAD_CYCLES", sequencer.id, insider.id, r1_cycles="many"),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert _experiment(session, "EXP_BAD_CYCLES") is None


def test_create_unknown_sequencer_is_404(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    """An unknown sequencer reference resolves to a controlled 404, not a FK error."""
    response = post_form(
        client,
        CREATE,
        _payload("EXP_GHOST_SEQUENCER", 999999, insider.id),
        token=insider_token,
    )

    assert response.status_code == 404
    assert _experiment(session, "EXP_GHOST_SEQUENCER") is None


def test_create_unknown_operator_is_404(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    """An unknown operator reference resolves to a controlled 404, not a FK error."""
    sequencer = create_sequencer(session)
    session.commit()

    response = post_form(
        client,
        CREATE,
        _payload("EXP_GHOST_OPERATOR", sequencer.id, 999999),
        token=insider_token,
    )

    assert response.status_code == 404
    assert _experiment(session, "EXP_GHOST_OPERATOR") is None


def test_edit_unknown_operator_is_404(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    experiment = create_experiment(session, insider, WORKFLOW)
    session.commit()

    response = post_form(
        client,
        _edit_path(experiment.id),
        _payload("EXP_EDITED_GHOST", experiment.sequencer_id, 999999),
        token=insider_token,
    )

    assert response.status_code == 404
    assert _reload(session, experiment).name == experiment.name


def test_create_denied_for_client(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    sequencer = create_sequencer(session)
    session.commit()
    before = session.count(Q.experiment.select())

    response = post_form(
        client,
        CREATE,
        _payload("EXP_CLIENT_CREATE", sequencer.id, user.id),
        token=user_token,
    )

    assert response.status_code == 403
    assert session.count(Q.experiment.select()) == before


def test_edit_persists_all_fields(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    experiment = create_experiment(session, insider, WORKFLOW)
    sequencer = create_sequencer(session)
    session.commit()

    response = post_form(
        client,
        _edit_path(experiment.id),
        _payload(
            "EXP_EDITED",
            sequencer.id,
            insider.id,
            workflow=C.ExperimentWorkFlow.NOVASEQ_6K_S4_XP.id,
            status=C.ExperimentStatus.SEQUENCING.id,
            r1_cycles="101",
            r2_cycles="99",
            i1_cycles="7",
            i2_cycles="6",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert_flash(response, "Experiment Updated!", category="success")

    updated = _reload(session, experiment)
    assert updated.name == "EXP_EDITED"
    assert updated.workflow == C.ExperimentWorkFlow.NOVASEQ_6K_S4_XP
    assert updated.status == C.ExperimentStatus.SEQUENCING
    assert updated.sequencer_id == sequencer.id
    assert updated.operator_id == insider.id
    assert updated.r1_cycles == 101
    assert updated.r2_cycles == 99
    assert updated.i1_cycles == 7
    assert updated.i2_cycles == 6


def test_edit_duplicate_name_rerenders(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    first = create_experiment(session, insider, WORKFLOW)
    second = create_experiment(session, insider, WORKFLOW)
    session.commit()

    response = post_form(
        client,
        _edit_path(first.id),
        _payload(second.name, first.sequencer_id, insider.id),
        token=insider_token,
    )

    assert_form_invalid(response, "An experiment with this name already exists.")
    assert _reload(session, first).name == first.name


def test_edit_keeping_own_name_is_allowed(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    experiment = create_experiment(session, insider, WORKFLOW)
    session.commit()

    response = post_form(
        client,
        _edit_path(experiment.id),
        _payload(experiment.name, experiment.sequencer_id, insider.id, status=C.ExperimentStatus.LOADED.id),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert _reload(session, experiment).status == C.ExperimentStatus.LOADED


def test_edit_unknown_experiment_is_404(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    sequencer = create_sequencer(session)
    session.commit()

    response = post_form(
        client,
        _edit_path(999999),
        _payload("EXP_MISSING", sequencer.id, insider.id),
        token=insider_token,
    )

    assert response.status_code == 404


def test_edit_denied_for_client(
    client: TestClient,
    session: SyncSession,
    insider,
    user,
    user_token: str,
):
    experiment = create_experiment(session, insider, WORKFLOW)
    session.commit()

    response = post_form(
        client,
        _edit_path(experiment.id),
        _payload("EXP_HIJACKED", experiment.sequencer_id, user.id),
        token=user_token,
    )

    assert response.status_code == 403
    assert _reload(session, experiment).name == experiment.name


def test_edit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    experiment = create_experiment(session, insider, WORKFLOW)
    session.commit()

    response = post_form_csrf_mismatch(
        client,
        _edit_path(experiment.id),
        _payload("EXP_CSRF", experiment.sequencer_id, insider.id),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert _reload(session, experiment).name == experiment.name


def test_edit_workflow_change_resizes_lanes(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    """The ``Experiment.workflow`` listener keeps lanes in sync with the flow cell."""
    experiment = create_experiment(session, insider, WORKFLOW)
    session.commit()
    initial_lanes = WORKFLOW.flow_cell_type.num_lanes
    assert len(_lanes(session, experiment.id)) == initial_lanes

    grown = C.ExperimentWorkFlow.NOVASEQ_X_10B_XP
    response = post_form(
        client,
        _edit_path(experiment.id),
        _payload(experiment.name, experiment.sequencer_id, insider.id, workflow=grown.id),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert _reload(session, experiment).workflow == grown
    assert len(_lanes(session, experiment.id)) == grown.flow_cell_type.num_lanes > initial_lanes

    response = post_form(
        client,
        _edit_path(experiment.id),
        _payload(experiment.name, experiment.sequencer_id, insider.id, workflow=WORKFLOW.id),
        token=insider_token,
    )

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    assert len(_lanes(session, experiment.id)) == initial_lanes