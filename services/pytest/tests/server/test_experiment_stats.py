"""Experiment stats tab: summary tiles, pool rows (sequenced vs planned flags, nested libraries), library rows
(per-lane bars, QC columns) and the undetermined row."""
import re
from html import unescape

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C

from ..db.create_units import create_seq_request, create_library, create_pool, create_experiment
from ._http import get


def _plan(session: SyncSession, experiment: models.Experiment, pool: models.Pool, lane_num: int, num_m_reads: float) -> None:
    lane = next(lane for lane in experiment.lanes if lane.number == lane_num)
    session.add(models.links.LanePoolLink(lane_id=lane.id, pool_id=pool.id, experiment_id=experiment.id, lane_num=lane_num, num_m_reads=num_m_reads))


def _reads(session: SyncSession, experiment: models.Experiment, library: models.Library | None, lane: int, num_reads: int, qc: dict | None = None) -> None:
    session.add(models.SeqQuality(
        lane=lane, num_reads=num_reads, library_id=library.id if library else None, experiment_id=experiment.id, qc=qc,
    ))


def _setup(session: SyncSession, user):
    """Pool A sequenced 80 M of 50 M planned (over), pool B 10 M of 100 M planned (under), 5 M undetermined."""
    seq_request = create_seq_request(session, user)
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    pool_a, pool_b = create_pool(session, user, seq_request), create_pool(session, user, seq_request)
    lib_1, lib_2, lib_3 = (create_library(session, user, seq_request) for _ in range(3))
    for library, pool in ((lib_1, pool_a), (lib_2, pool_a), (lib_3, pool_b)):
        library.pool_id = pool.id
    for pool in (pool_a, pool_b):
        pool.experiment_id = experiment.id
    _plan(session, experiment, pool_a, 1, 50)
    _plan(session, experiment, pool_b, 2, 100)
    _reads(session, experiment, lib_1, 1, 30_000_000, qc={"q30": 0.9})
    _reads(session, experiment, lib_1, 2, 30_000_000, qc={"q30": 0.8})
    _reads(session, experiment, lib_2, 1, 20_000_000)
    _reads(session, experiment, lib_3, 2, 10_000_000)
    _reads(session, experiment, None, 1, 5_000_000)
    session.commit()
    return experiment, pool_a, pool_b, lib_1, lib_2, lib_3


def _pool_row(html: str, pool: models.Pool) -> str:
    match = re.search(rf'<tbody data-sort-unit data-name="{re.escape(pool.name.lower())}".*?</tbody>', html, re.S)
    assert match, f"no row for pool {pool.name}"
    return match.group(0)


def test_experiment_stats(client: TestClient, session: SyncSession, user, insider_token: str):
    experiment, pool_a, pool_b, lib_1, lib_2, lib_3 = _setup(session, user)
    response = get(client, f"/htmx/experiments/{experiment.id}/stats", insider_token)
    assert response.status_code == 200, response.text
    html = response.text

    # summary: 95 M total, 90 M in libraries, 5 M (5.3 %) undetermined
    assert "95.0 M" in html and "90.0 M" in html and "5.3 %" in html

    row_a, row_b = _pool_row(html, pool_a), _pool_row(html, pool_b)
    assert f"/pools/{pool_a.id}" in row_a and "from=experiment" in row_a
    assert 'badge badge-warning">160.0 %' in row_a
    assert 'badge badge-danger">10.0 %' in row_b
    # a pool's libraries are nested under it, largest first
    assert row_a.index(lib_1.name) < row_a.index(lib_2.name) and lib_3.name not in row_a
    # pool bars are the share of the whole flow cell (95 M), library bars the share of their pool
    assert 'es-bar-fill " style="width: 84.21%;"' in row_a  # pool A: 80 M
    assert 'is-pool-share" style="width: 75.00%;"' in row_a  # its library 1: 60 of 80 M
    assert 'is-pool-share" style="width: 25.00%;"' in row_a  # its library 2: 20 of 80 M
    assert "75.0 % of pool reads" in row_a
    assert 'es-bar-fill " style="width: 10.53%;"' in row_b  # pool B: 10 M
    assert lib_3.name in row_b

    # pools sorted by reads, undetermined pinned last
    assert html.index(pool_a.name) < html.index(pool_b.name) < html.index('data-pin-last data-filter="undetermined"')

    # libraries: per-lane segments and QC column (read-weighted average over lanes)
    # hovering a lane segment: the lane's reads and its share of the library's reads
    for lane in (1, 2):
        assert f"<b>Lane {lane}</b><br>30 000 000 reads (30.0 M)<br>50.0 % of library reads" in unescape(html)
    assert "<b>Lane 1</b><br>5 000 000 reads (5.0 M)<br>100.0 % of undetermined reads" in unescape(html)
    assert re.search(r'data-sort-key="qc0" data-sort-type="num">\s*<div class="es-col-header">\s*<span>q30</span>', html)
    assert 'data-qc0="0.85"' in html
    assert re.search(r'class="es-undetermined">\s*<td>Undetermined</td>', html)
    assert "Lane 1</span>" in html and "Lane 2</span>" in html


def test_experiment_stats_empty(client: TestClient, session: SyncSession, user, insider_token: str):
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    session.commit()
    response = get(client, f"/htmx/experiments/{experiment.id}/stats", insider_token)
    assert response.status_code == 200, response.text
    assert "No demultiplexing stats yet." in response.text


def test_experiment_stats_requires_insider(client: TestClient, session: SyncSession, user, user_token: str):
    experiment, *_ = _setup(session, user)
    response = get(client, f"/htmx/experiments/{experiment.id}/stats", user_token)
    assert response.status_code == 403
