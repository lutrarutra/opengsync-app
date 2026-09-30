"""Actions and workflows that were insider- or admin-only in legacy Flask stay that way.

The ``/htmx`` routers only require a login, so each action has to enforce the
role itself. Two checks per action:

- every route of the action (GET and POST) has ``require_insider``/``require_admin``
  in its dependency tree. POST is checked this way because an empty POST can be
  rejected by form validation (202) before the role check runs, which would hide
  a missing check.
- a real GET: a client gets 403, the required role gets past the check.

Actions that legacy opened to clients with WRITE access on the entity (sample
attributes, library features, share project data, reseq, submit request, share
emails, barcode clashes on a request) are tested in their own modules instead.
"""

from dataclasses import dataclass

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C

from server.core import dependencies

from ..db.create_units import (
    create_experiment, create_feature_kit, create_index_kit, create_lab_prep, create_pool,
    create_project, create_protocol, create_seq_request,
)
from ._http import get

INSIDER = (dependencies.require_insider, dependencies.require_admin)
ADMIN = (dependencies.require_admin,)


@dataclass(frozen=True)
class Spec:
    prefix: str  # route-name prefix: an action class, or a workflow class for all its steps
    role: str  # "insider" or "admin"
    params: tuple[tuple[str, str], ...] = ()  # path param -> entity key
    query: tuple[tuple[str, str], ...] = ()
    get_route: str | None = "Begin"  # GET route to call for real; None to only check dependencies

    def __str__(self) -> str:
        return self.prefix


SPECS = [
    Spec("StoreSamplesAction", "insider"),
    Spec("MergeProjectsAction", "insider"),
    Spec("SamplePoolingAction", "insider", (("lab_prep_id", "lab_prep"),)),
    Spec("DilutePoolsAction", "insider", (("experiment_id", "separate_experiment"),)),
    Spec("BarcodeConstraintsAction", "insider"),
    Spec("UploadLibraryPrepSpreadsheetAction", "insider", (("lab_prep_id", "lab_prep"),)),
    Spec("AddKitsToProtocolAction", "insider", (("protocol_id", "protocol"),)),
    Spec("EditKitFeaturesAction", "insider", (("feature_kit_id", "feature_kit"),)),  # legacy: admin
    Spec("EditKitBarcodesForm", "admin", (("index_kit_id", "index_kit"),)),
    Spec("GenerateSequencerLoadingChecklistAction", "insider", (("experiment_id", "separate_experiment"),)),
    Spec("BillingAction", "insider"),
    Spec("SetExperimentCyclesAction", "insider", (("experiment_id", "separate_experiment"),)),
    Spec("SelectExperimentPoolsAction", "insider", (("experiment_id", "separate_experiment"),)),
    Spec("SelectPoolLibrariesAction", "insider", (("pool_id", "pool"),)),
    Spec("LibraryPrepAction", "insider", (("lab_prep_id", "lab_prep"),)),
    Spec("ProcessSeqRequestAction", "insider", (("seq_request_id", "seq_request"),)),
    Spec("AddSeqRequestAssigneeAction", "insider", (("seq_request_id", "seq_request"),)),
    Spec("AddProjectAssigneeAction", "insider", (("project_id", "project"),)),
    Spec("ShareDirectoryAction", "insider"),
    Spec("AssociatePathAction", "insider", query=(("path", "some/file.txt"),)),
    Spec("LanePoolsCombinedAction", "insider", (("experiment_id", "combined_experiment"),)),
    Spec("LanePoolsSeparateAction", "insider", (("experiment_id", "separate_experiment"),)),
    Spec("LoadFlowCellCombinedAction", "insider", (("experiment_id", "combined_experiment"),)),
    Spec("LoadFlowCellSeparateAction", "insider", (("experiment_id", "separate_experiment"),)),
    Spec("DistributeReadsCombinedAction", "insider", (("experiment_id", "combined_experiment"),)),
    Spec("DistributeReadsSeparateAction", "insider", (("experiment_id", "separate_experiment"),)),
    # Multi-step workflows: every step must check, since steps can be posted to directly.
    Spec("BAReportWorkflow", "insider", get_route=None),
    Spec("QubitMeasureWorkflow", "insider", get_route=None),
]


def _routes(app, prefix: str) -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute) and r.name.startswith(f"{prefix}.")]


def _dependency_calls(dependant):
    for dep in dependant.dependencies:
        yield dep.call
        yield from _dependency_calls(dep)


@pytest.mark.parametrize("spec", SPECS, ids=str)
def test_every_route_requires_role(client: TestClient, spec: Spec):
    routes = _routes(client.app, spec.prefix)
    assert routes, f"no routes named {spec.prefix}.*"
    required = ADMIN if spec.role == "admin" else INSIDER

    unguarded = [
        f"{','.join(sorted(r.methods))} {r.path} [{r.name}]"
        for r in routes
        if not any(call in required for call in _dependency_calls(r.dependant))
    ]
    assert not unguarded, f"missing {spec.role} check:\n" + "\n".join(unguarded)


@pytest.fixture
def entities(session: SyncSession, user: models.User, insider: models.User) -> dict[str, int]:
    """Client-owned project/request/pool, so a 403 comes from the role check, not ownership."""
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    ids = {
        "project": project.id,
        "seq_request": seq_request.id,
        "pool": create_pool(session, user, seq_request).id,
        "lab_prep": create_lab_prep(session, insider).id,
        "protocol": create_protocol(session).id,
        "feature_kit": create_feature_kit(session).id,
        "index_kit": create_index_kit(session).id,
        "combined_experiment": create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_S1_STD).id,
        "separate_experiment": create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_S1_XP).id,
    }
    session.commit()
    return ids


def _get_url(client: TestClient, spec: Spec, entities: dict[str, int]) -> str:
    params = {name: entities[key] for name, key in spec.params}
    return str(client.app.url_path_for(f"{spec.prefix}.{spec.get_route}", **params))


@pytest.mark.parametrize("spec", [s for s in SPECS if s.get_route], ids=str)
def test_client_is_denied(client: TestClient, entities, user_token: str, spec: Spec):
    response = get(client, _get_url(client, spec, entities), user_token, params=dict(spec.query))
    assert response.status_code == 403, response.text[:300]


@pytest.mark.parametrize("spec", [s for s in SPECS if s.get_route], ids=str)
def test_required_role_passes_the_check(
    client: TestClient, entities, insider_token: str, admin_token: str, spec: Spec,
):
    # Some of these templates are not ported yet and raise; only access is asserted here.
    lenient = TestClient(client.app, raise_server_exceptions=False)
    token = admin_token if spec.role == "admin" else insider_token
    response = get(lenient, _get_url(client, spec, entities), token, params=dict(spec.query))
    assert response.status_code not in (303, 401, 403), response.text[:300]


@pytest.mark.parametrize("spec", [s for s in SPECS if s.role == "admin" and s.get_route], ids=str)
def test_insider_is_denied_admin_only_action(client: TestClient, entities, insider_token: str, spec: Spec):
    response = get(client, _get_url(client, spec, entities), insider_token, params=dict(spec.query))
    assert response.status_code == 403
