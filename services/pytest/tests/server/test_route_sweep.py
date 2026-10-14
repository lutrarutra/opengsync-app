"""Route sweeps (§5): GET routes do not write and pages render whole documents; no route answers an
invalid parameter with a 500.

The GET sweep requests each GET route of the app with its path ids filled from one set of objects,
once without query parameters and once per context id it accepts (``seq_request_id``, ...),
as admin, as a client user and with ids that do not exist. Committed writes are read from the
audit log, which records every committed change of a request (``DBSessionCleanupMiddleware``).

``SameSite=Lax`` still sends the login cookie on cross-site top-level GET navigation and the
CSRF check only covers state-changing methods, so a GET that writes would be open to CSRF.

The invalid-parameter sweeps send junk (non-numeric, negative, empty, beyond the database integer
range) as every query parameter of every GET route, and as path and query parameters of every
state-changing route (with an empty body); each must be answered with a controlled 4xx.
"""

import io
import re
from collections.abc import Iterator

import openpyxl
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from loguru import logger

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ..db.create_units import (
    create_experiment, create_feature_kit, create_file, create_group, create_index_kit, create_kit,
    create_lab_prep, create_library, create_plate, create_pool, create_project, create_protocol,
    create_sample, create_seq_request, create_seq_run, create_sequencer,
)
from ._http import CSRF, cookie_header, get

CONTEXT_PARAMS = (
    "seq_request_id", "project_id", "lab_prep_id", "experiment_id", "pool_id", "library_id",
    "sample_id", "user_id", "index_kit_id", "group_id",
)
MISSING_ID = 999999
OUT_OF_RANGE = "99999999999999999999"  # parses as int, overflows the integer columns
# fragments outside /htmx that their page loads with hx-get
PAGE_FRAGMENT_ROUTES = {"shared_browser_entries"}


def _routes(routes, prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            yield from _routes(route.original_router.routes, prefix + (route.include_context.prefix or ""))
        elif isinstance(route, APIRoute):
            yield prefix + route.path, route


def _query_params(dependant) -> Iterator[str]:
    for param in dependant.query_params:
        yield param.name
    for dependency in dependant.dependencies:
        yield from _query_params(dependency)


@pytest.fixture
def audit_records():
    records: list[dict] = []
    sink_id = logger.add(
        lambda message: records.append(dict(message.record["extra"])),
        filter=lambda record: record["extra"].get("audit") is True,
        level="INFO",
    )
    yield records
    logger.remove(sink_id)


def _ids(session: SyncSession, owner: models.User) -> dict:
    project = create_project(session, owner)
    seq_request = create_seq_request(session, owner)
    library = create_library(session, owner, seq_request)
    pool = create_pool(session, owner, seq_request)
    library.pool_id = pool.id
    media_file = create_file(session, seq_request=seq_request)
    share = session.save(Q.share_token.create(owner=owner, time_valid_min=60, paths=["shared"]), flush=True)
    ids = dict(
        project_id=project.id, seq_request_id=seq_request.id, library_id=library.id, pool_id=pool.id,
        sample_id=create_sample(session, owner, project).id,
        experiment_id=create_experiment(session, owner, C.ExperimentWorkFlow.as_list()[0]).id,
        lab_prep_id=create_lab_prep(session, owner).id,
        feature_kit_id=create_feature_kit(session).id, index_kit_id=create_index_kit(session).id,
        kit_id=create_kit(session).id, protocol_id=create_protocol(session).id,
        seq_run_id=create_seq_run(session).id, sequencer_id=create_sequencer(session).id,
        group_id=create_group(session).id, plate_id=create_plate(session, owner).id,
        media_file_id=media_file.id, file_id=media_file.id, data_path_id=1, service_type_id=0,
        user_id=owner.id, msg_id="unknown", token=share.uuid, subpath="",
    )
    session.commit()
    return ids


@pytest.mark.parametrize("mode", ["admin", "client", "missing-ids"])
def test_get_routes_do_not_write_or_crash(
    client: TestClient, session: SyncSession, admin, admin_token: str, user_token: str, audit_records: list[dict], mode: str,
):
    ids = _ids(session, admin)
    if mode == "missing-ids":
        ids = {name: MISSING_ID if isinstance(value, int) else value for name, value in ids.items()}
    token = user_token if mode == "client" else admin_token

    writes, errors, fragments, requested = [], [], [], 0
    for path, route in _routes(client.app.routes):
        if "GET" not in route.methods:
            continue
        url = re.sub(r"{(\w+)(?::\w+)?}", lambda m: str(ids.get(m.group(1), 1)), path)
        names = set(_query_params(route.dependant))
        for params in [{}] + [{name: ids[name]} for name in CONTEXT_PARAMS if name in names]:
            if "uuid" in names:
                params |= {"uuid": "00000000-0000-0000-0000-000000000001"}
            audit_records.clear()
            try:
                response = get(client, url, token, params=params)
                status = response.status_code
                # a page (not /htmx or /api) opened in the browser renders a whole document, error pages included
                if (
                    not path.startswith(("/htmx/", "/api/")) and route.name not in PAGE_FRAGMENT_ROUTES
                    and "text/html" in response.headers.get("content-type", "")
                    and "<html" not in response.text
                ):
                    fragments.append(f"{path} {params}: {status}")
            except Exception as e:  # TestClient re-raises unhandled server errors
                status = f"{type(e).__name__}: {e}"
            requested += 1
            if not isinstance(status, int) or status >= 500:
                errors.append(f"{path} {params}: {status}")
            changes = [change for record in audit_records if record["method"] == "GET" for change in record["changes"]]
            if changes:
                writes.append(f"{path} {params}: {changes}")

    assert requested > 400
    assert writes == []
    assert errors == []
    assert fragments == []


def _status(send) -> int | str:
    try:
        return send().status_code
    except Exception as e:  # TestClient re-raises unhandled server errors
        return f"{type(e).__name__}: {e}"[:300]


@pytest.mark.parametrize("junk", ["zz", "-1", "", OUT_OF_RANGE])
def test_invalid_query_values_are_rejected_cleanly(client: TestClient, session: SyncSession, admin, admin_token: str, junk: str):
    ids = _ids(session, admin)
    errors = []
    for path, route in _routes(client.app.routes):
        if "GET" not in route.methods:
            continue
        url = re.sub(r"{(\w+)(?::\w+)?}", lambda m: str(ids.get(m.group(1), 1)), path)
        params = {name: junk for name in _query_params(route.dependant)}
        status = _status(lambda: get(client, url, admin_token, params=params))
        if not isinstance(status, int) or status >= 500:
            errors.append(f"{path}: {status}")

    assert errors == []


@pytest.mark.parametrize("junk", [None, "zz", OUT_OF_RANGE], ids=["real-ids", "zz", "out-of-range"])
def test_state_changing_routes_do_not_crash(client: TestClient, session: SyncSession, admin, admin_token: str, junk: str | None):
    """An empty body with real ids, or junk as every path and query parameter."""
    ids = _ids(session, admin)
    headers = cookie_header(client, admin_token, csrf_token=CSRF) | {"X-CSRF-Token": CSRF}
    errors = []
    for path, route in _routes(client.app.routes):
        for method in sorted(route.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            if junk is None:
                url, params = re.sub(r"{(\w+)(?::\w+)?}", lambda m: str(ids.get(m.group(1), 1)), path), {}
            else:
                url = re.sub(r"{(\w+)(?::\w+)?}", lambda m: "" if m.group(1) == "subpath" else junk, path)
                params = {name: junk for name in _query_params(route.dependant)}
            status = _status(lambda: client.request(
                method, url, headers=headers, params=params, data={"csrf_token": CSRF}, follow_redirects=False,
            ))
            if not isinstance(status, int) or status >= 500:
                errors.append(f"{method} {path}: {status}")

    assert errors == []


# ── Fixes found by the sweep ────────────────────────────────────────────────


def test_seq_run_page_renders_the_run(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_run = create_seq_run(session)
    experiment = create_experiment(session, insider, C.ExperimentWorkFlow.as_list()[0])
    seq_run.experiment_name = experiment.name
    session.save(seq_run, flush=True)
    session.commit()

    response = get(client, f"/seq_runs/{seq_run.id}", insider_token)
    assert response.status_code == 200, response.text
    assert seq_run.flowcell_id in response.text
    assert f"/experiments/{experiment.id}" in response.text

    from_experiment = get(client, f"/seq_runs/{seq_run.id}", insider_token, params={"from": f"experiment@{experiment.id}"})
    assert from_experiment.status_code == 200
    assert "Experiments" in from_experiment.text


def test_seq_run_page_is_insider_only_and_404s(client: TestClient, session: SyncSession, user_token: str, insider_token: str):
    seq_run = create_seq_run(session)
    session.commit()

    assert get(client, f"/seq_runs/{seq_run.id}", user_token).status_code == 403
    assert get(client, f"/seq_runs/{MISSING_ID}", insider_token).status_code == 404


@pytest.mark.parametrize("value", ["project", "project@", "project@abc", "@", "a@b@c"])
def test_malformed_from_parameter_is_ignored(client: TestClient, session: SyncSession, user, user_token: str, value: str):
    project = create_project(session, user)
    session.commit()

    assert get(client, f"/projects/{project.id}", user_token, params={"from": value}).status_code == 200


def test_seq_request_export_is_a_workbook(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user)
    create_library(session, user, seq_request)
    session.commit()

    response = get(client, f"/htmx/seq_requests/{seq_request.id}/export", user_token)

    assert response.status_code == 200
    assert f"request_{seq_request.id}.xlsx" in response.headers["content-disposition"]
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    assert workbook.sheetnames == ["metadata", "libraries", "features"]


@pytest.mark.parametrize("path, param", [
    ("/htmx/projects/create", "project_id"),
    ("/htmx/seq_requests/create", "seq_request_id"),
    ("/htmx/lab_preps/create", "lab_prep_id"),
    ("/htmx/pools/create", "pool_id"),
    ("/htmx/experiments/create", "experiment_id"),
    ("/htmx/groups/create", "group_id"),
])
def test_create_form_ignores_a_stray_id(client: TestClient, admin_token: str, path: str, param: str):
    response = get(client, path, admin_token, params={param: 1})

    assert response.status_code == 200, response.text
    assert "/edit" not in response.text


@pytest.mark.parametrize("path", ["/htmx/flow_cell_design/edit-flow-cell-design", "/htmx/pool_design/edit-pool-design"])
def test_design_edit_without_id_is_400(client: TestClient, insider_token: str, path: str):
    assert get(client, path, insider_token).status_code == 400


def test_user_table_filtered_by_group(client: TestClient, session: SyncSession, admin, admin_token: str, user):
    group = create_group(session)
    session.save(Q.affiliation.create(user=user, group=group, type=C.AffiliationType.MEMBER), flush=True)
    session.commit()

    response = get(client, "/htmx/users/render-table-page", admin_token, params={"group_id": group.id})

    assert response.status_code == 200, response.text
    assert user.email in response.text
    assert admin.email not in response.text


def test_group_table_filtered_by_user(client: TestClient, session: SyncSession, admin_token: str, user, user_2_token: str):
    member_of, other = create_group(session), create_group(session)
    session.save(Q.affiliation.create(user=user, group=member_of, type=C.AffiliationType.MEMBER), flush=True)
    session.commit()

    response = get(client, "/htmx/groups/render-table-page", admin_token, params={"user_id": user.id})
    assert response.status_code == 200, response.text
    assert member_of.name in response.text and other.name not in response.text

    assert get(client, "/htmx/groups/render-table-page", user_2_token, params={"user_id": user.id}).status_code == 403


@pytest.mark.parametrize("path", ["/htmx/files/render-table-page", "/htmx/lanes/render-table-page"])
def test_table_without_context_is_400(client: TestClient, admin_token: str, path: str):
    assert get(client, path, admin_token).status_code == 400


def test_expired_workflow_state_is_400(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    session.commit()

    response = get(
        client, client.app.url_path_for("IndexCheckWorkflow.VerifyOrientationsForm.Previous"), insider_token,  # type: ignore[attr-defined]
        params={"seq_request_id": seq_request.id, "uuid": "00000000-0000-0000-0000-000000000001"},
    )

    assert response.status_code == 400
    assert "expired" in response.text


def test_out_of_range_id_is_422(client: TestClient, user_token: str):
    assert get(client, f"/projects/{OUT_OF_RANGE}", user_token).status_code == 422
    assert get(client, "/htmx/files/render-table-page", user_token, params={"seq_request_id": OUT_OF_RANGE}).status_code == 422


@pytest.mark.parametrize("mux_type_id", [-1, MISSING_ID])
def test_mux_prep_with_unknown_mux_type_is_400(client: TestClient, session: SyncSession, insider, insider_token: str, mux_type_id: int):
    lab_prep = create_lab_prep(session, insider)
    session.commit()

    response = get(client, f"/htmx/lab_preps/{lab_prep.id}/mux-prep", insider_token, params={"mux_type_id": mux_type_id})

    assert response.status_code == 400


def test_make_owner_of_group_without_owner(client: TestClient, session: SyncSession, admin_token: str, user):
    """Staff can name an owner for a group that has none (its owner affiliation was removed)."""
    group = create_group(session)
    session.save(Q.affiliation.create(user=user, group=group, type=C.AffiliationType.MEMBER), flush=True)
    session.commit()

    response = client.post(
        f"/htmx/groups/{group.id}/make-owner/{user.id}",
        headers=cookie_header(client, admin_token, csrf_token=CSRF) | {"X-CSRF-Token": CSRF}, follow_redirects=False,
    )

    assert response.status_code == 204, response.text
    session.expire_all()
    assert session.get_one(Q.group.select(id=group.id)).owner.id == user.id
