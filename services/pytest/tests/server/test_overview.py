"""Overview graphs (JSON for static/js/overview-graph.js) of requests, projects and experiments."""
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C

from ..db.create_units import create_seq_request, create_library, create_project, create_sample, create_pool, create_experiment
from ._http import get


def _link(session: SyncSession, sample: models.Sample, library: models.Library) -> None:
    session.add(models.links.SampleLibraryLink(sample_id=sample.id, library_id=library.id))


def _setup(session: SyncSession, user):
    """A request with two samples of one project: one library pooled and on lane 2 of an experiment, one not."""
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    pooled, unpooled = create_library(session, user, seq_request), create_library(session, user, seq_request)
    pooled.pool_id = pool.id
    pooled.status = C.LibraryStatus.SEQUENCED
    pooled.seq_depth_requested = 20
    pool.experiment_id = pooled.experiment_id = experiment.id  # as linking the pool to the experiment does
    for library in (pooled, unpooled):
        sample = create_sample(session, user, project)
        sample.status = C.SampleStatus.STORED
        _link(session, sample, library)
    lane = next(lane for lane in experiment.lanes if lane.number == 2)
    session.add(models.links.LanePoolLink(lane_id=lane.id, pool_id=pool.id, experiment_id=experiment.id, lane_num=2, num_m_reads=300))
    session.add(models.SeqQuality(lane=2, num_reads=12_000_000, library_id=pooled.id, experiment_id=experiment.id))
    session.commit()
    return project, seq_request, pool, experiment, pooled, unpooled


def _edges(data) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in data["edges"]}


def test_request_overview(client: TestClient, session: SyncSession, user, user_token: str, insider_token: str):
    project, seq_request, pool, experiment, pooled, unpooled = _setup(session, user)
    response = get(client, f"/htmx/seq_requests/{seq_request.id}/overview", user_token)
    assert response.status_code == 200, response.text
    data = response.json()
    assert [c["kind"] for c in data["columns"]] == ["project", "sample", "library", "pool", "experiment"]
    nodes = {n["id"]: n for n in data["nodes"]}

    library = nodes[f"library-{pooled.id}"]
    assert library["status"] == C.LibraryStatus.SEQUENCED.id
    assert data["statuses"]["library"][str(C.LibraryStatus.SEQUENCED.id)] == {"label": "Sequenced", "icon": "✅", "tone": "done"}
    assert library["metrics"] == {"reads": 12_000_000, "requested": 20_000_000}
    assert ["Reads", "12.0 M"] in library["facts"]
    assert data["groups"][library["group"]] == f"pool {pool.name}"
    assert data["groups"][nodes[f"library-{unpooled.id}"]["group"]] == "not pooled"
    pool_node = nodes[f"pool-{pool.id}"]
    assert pool_node["sub"] == "1 library"
    # the pool's type goes next to its name; its reads are those of its libraries in its experiment
    assert pool_node["aside"] == pool.type.label
    assert pool_node["metrics"] == {"reads": 12_000_000} and ["Reads", "12.0 M"] in pool_node["facts"]
    # the pool's lanes go on its edge to the experiment
    assert {"source": f"pool-{pool.id}", "target": f"experiment-{experiment.id}", "lanes": [2]} in data["edges"]

    samples = [n for n in data["nodes"] if n["kind"] == "sample"]
    # libraries of the sample in this request / all of its libraries
    assert [n["sub"] for n in samples] == ["1/1 library", "1/1 library"]
    assert ["Libraries", "1 in this request, 1 in total"] in samples[0]["facts"]
    sample_ids = [n["id"] for n in samples]
    assert len(sample_ids) == 2 and all((f"project-{project.id}", s) in _edges(data) for s in sample_ids)
    assert (f"library-{pooled.id}", f"pool-{pool.id}") in _edges(data)
    assert (f"pool-{pool.id}", f"experiment-{experiment.id}") in _edges(data)

    # clients get no links to insider pages (experiments), insiders do
    assert "experiment" not in data["links"] and data["links"]["library"].endswith("/libraries/{id}")
    assert get(client, f"/htmx/seq_requests/{seq_request.id}/overview", insider_token).json()["links"]["experiment"].endswith("/experiments/{id}")


def test_request_overview_denied_to_others(client: TestClient, session: SyncSession, insider, user_token: str):
    seq_request = create_seq_request(session, insider)
    session.commit()
    assert get(client, f"/htmx/seq_requests/{seq_request.id}/overview", user_token).status_code == 403


def test_project_overview(client: TestClient, session: SyncSession, user, user_token: str):
    project, seq_request, pool, _, pooled, _ = _setup(session, user)
    lonely = create_sample(session, user, project)
    session.commit()
    data = get(client, f"/htmx/projects/{project.id}/overview", user_token).json()
    assert [c["kind"] for c in data["columns"]] == ["sample", "library", "pool", "experiment"]
    nodes = {n["id"]: n for n in data["nodes"]}
    assert data["groups"][nodes[f"sample-{lonely.id}"]["group"]] == "no libraries"
    assert nodes[f"sample-{lonely.id}"]["sub"] == "0 libraries"
    # libraries are grouped by request and pool, and samples follow their first library
    assert data["groups"][nodes[f"library-{pooled.id}"]["group"]] == f"{seq_request.identifier} · pool {pool.name}"
    linked = next(s for s, t in _edges(data) if t == f"library-{pooled.id}")
    assert nodes[linked]["group"] == nodes[f"library-{pooled.id}"]["group"]


def test_experiment_overview(client: TestClient, session: SyncSession, user, insider_token: str, user_token: str):
    _, seq_request, pool, experiment, pooled, unpooled = _setup(session, user)
    response = get(client, f"/htmx/experiments/{experiment.id}/overview", insider_token)
    assert response.status_code == 200, response.text
    data = response.json()
    assert [c["kind"] for c in data["columns"]] == ["seq_request", "library", "pool", "lane"]
    nodes = {n["id"]: n for n in data["nodes"]}
    assert f"library-{unpooled.id}" not in nodes  # not on the experiment
    lane = next(lane for lane in experiment.lanes if lane.number == 2)
    assert nodes[f"lane-{lane.id}"]["sub"] == "1 pool · 12.0 M reads"
    assert nodes[f"lane-{lane.id}"]["ref"] == experiment.id  # links to the experiment
    assert nodes[f"pool-{pool.id}"]["metrics"]["reads"] == 12_000_000
    assert "metrics" not in nodes[f"seq_request-{seq_request.id}"]
    assert len([n for n in data["nodes"] if n["kind"] == "lane"]) == len(experiment.lanes)
    assert {(f"seq_request-{seq_request.id}", f"library-{pooled.id}"), (f"library-{pooled.id}", f"pool-{pool.id}"),
            (f"pool-{pool.id}", f"lane-{lane.id}")} <= _edges(data)

    assert get(client, f"/htmx/experiments/{experiment.id}/overview", user_token).status_code in (302, 303, 403)
    assert get(client, "/htmx/experiments/999999/overview", insider_token).status_code == 404


def test_pages_open_the_graph_in_a_popup(client: TestClient, session: SyncSession, user, insider_token: str):
    project, seq_request, _, experiment, _, _ = _setup(session, user)
    for page, popup, overview in (
        (f"/seq_requests/{seq_request.id}", "request-overview", f"/htmx/seq_requests/{seq_request.id}/overview"),
        (f"/projects/{project.id}", "project-overview", f"/htmx/projects/{project.id}/overview"),
        (f"/experiments/{experiment.id}", "experiment-overview", f"/htmx/experiments/{experiment.id}/overview"),
    ):
        text = get(client, page, insider_token).text
        assert "js/overview-graph.js" in text and overview in text
        # a button on the title line opens the full-screen popup; there is no Overview tab any more
        assert f'data-bs-toggle="modal" data-bs-target="#{popup}"' in text and f'id="{popup}"' in text
        assert f"#{popup}-tab" not in text
    # the experiment's popup switches between its graph and those of its projects, one each
    other = create_project(session, user)  # nothing on the experiment
    session.commit()
    text = get(client, f"/experiments/{experiment.id}", insider_token).text
    assert 'name="experiment-overview-view"' in text and text.count('class="btn-check" name="experiment-overview-view"') == 2
    assert f'/htmx/projects/{project.id}/overview"' in text and f"/htmx/projects/{other.id}/overview" not in text
    assert 'name="project-overview-view"' not in get(client, f"/projects/{project.id}", insider_token).text
