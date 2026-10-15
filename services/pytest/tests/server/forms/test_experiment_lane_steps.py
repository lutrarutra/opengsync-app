"""Experiment lane steps: lane pooling, read distribution and flow-cell loading.

As legacy (``lane_pools``, ``dist_reads``, ``load_flow_cell`` workflows), each in a Combined
(one set of values for all lanes) and a Separate (per lane) variant:

- Lane pooling: reads per pool (combined: total over all lanes, stored per lane), the dilution
  to pipet from, target molarity and volume per lane; saves a lane pooling table (TSV) with
  the pipetting volumes and comments it on the experiment.
- Read distribution: reads per pool (combined) or per pool and lane (separate); combined skips
  empty cells, separate clears them.
- Flow-cell loading: phi-X, target molarity, total volume and the qubit after dilution per lane;
  the library volume follows from the lane molarity; the experiment becomes LOADED once every
  lane is loaded.

Routing and access are in ``test_experiment_lane_actions.py``.
"""

import os
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C, actions

from server.core import config

from ...db.create_units import create_experiment, create_pool, create_seq_request
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form

PREFIX = "/htmx/experiments"
COMBINED = C.ExperimentWorkFlow.NOVASEQ_6K_S1_STD  # 2 lanes
SEPARATE = C.ExperimentWorkFlow.NOVASEQ_6K_S1_XP   # 2 lanes
QUBIT, SIZE = 2.0, 400
MOLARITY = QUBIT / (SIZE * 660) * 1_000_000


@pytest.fixture
def media_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config.settings.app_config, "media_folder", str(tmp_path))
    return tmp_path


class Setup:
    """An experiment with two pools (requested 100 and 300 M reads) on both lanes."""

    def __init__(self, session: SyncSession, user: models.User, insider: models.User, workflow: C.ExperimentWorkFlow):
        self.session = session
        self.experiment = create_experiment(session, insider, workflow)
        seq_request = create_seq_request(session, user)
        self.pools = []
        for reads in (100.0, 300.0):
            pool = create_pool(session, user, seq_request)
            pool.num_m_reads_requested, pool.qubit_concentration, pool.avg_fragment_size = reads, QUBIT, SIZE
            session.save(pool, flush=True)
            actions.link_pool_experiment(session, self.experiment, pool)
            if not workflow.combined_lanes:
                for lane in self.experiment.lanes:
                    actions.add_pool_to_lane(session, self.experiment, pool, lane)
            self.pools.append(pool)
        session.commit()
        self.a, self.b = self.pools

    def path(self, step: str) -> str:
        variant = "combined" if self.experiment.workflow.combined_lanes else "separate"
        return f"{PREFIX}/{self.experiment.id}/{step}/{variant}"

    def lanes(self) -> list[models.Lane]:
        self.session.expire_all()
        return sorted(self.session.get_all(Q.lane.select(experiment_id=self.experiment.id), limit=None), key=lambda lane: lane.number)

    def links(self) -> dict[tuple[int, int], models.links.LanePoolLink]:
        """(lane number, pool id) -> link."""
        self.session.expire_all()
        experiment = self.session.get_one(Q.experiment.select(id=self.experiment.id))
        return {(link.lane_num, link.pool_id): link for link in experiment.laned_pool_links}

    def reads(self) -> dict[tuple[int, int], float | None]:
        return {key: link.num_m_reads for key, link in self.links().items()}

    def status(self) -> C.ExperimentStatus:
        self.session.expire_all()
        return self.session.get_one(Q.experiment.select(id=self.experiment.id)).status


@pytest.fixture
def combined(session: SyncSession, user, insider) -> Setup:
    return Setup(session, user, insider, COMBINED)


@pytest.fixture
def separate(session: SyncSession, user, insider) -> Setup:
    return Setup(session, user, insider, SEPARATE)


def _pooling_tables(session: SyncSession, setup: Setup, media_folder: Path) -> list[pd.DataFrame]:
    session.expire_all()
    files = session.get_all(Q.media_file.select(experiment_id=setup.experiment.id), limit=None)
    files = [f for f in files if f.type == C.MediaFileType.LANE_POOLING_TABLE]
    return [pd.read_csv(media_folder / f.path, sep="\t") for f in files]


# ── Lane pooling: combined ──────────────────────────────────────────────────


def _combined_pooling_payload(setup: Setup, reads=(200.0, 600.0), dilutions=("Orig.", "Orig."), molarity="3", volume="50") -> dict:
    payload = {"target_molarity": molarity, "target_total_volume": volume}
    for i, (pool, m_reads, dilution) in enumerate(zip(setup.pools, reads, dilutions)):
        payload |= {f"sample_sub_forms-{i}-pool_id": str(pool.id), f"sample_sub_forms-{i}-m_reads": str(m_reads), f"sample_sub_forms-{i}-dilution": dilution}
    return payload


def test_combined_pooling_renders_total_reads_per_pool(client: TestClient, combined: Setup, insider_token: str):
    response = get(client, combined.path("lane-pools"), insider_token)

    assert response.status_code == 200, response.text
    # Stored per lane (requested / 2), shown as the total over both lanes
    assert 'name="sample_sub_forms-0-m_reads"' in response.text
    assert 'value="100.0"' in response.text and 'value="300.0"' in response.text
    assert combined.a.name in response.text and combined.b.name in response.text


def test_combined_pooling_prefers_the_latest_dilution(
    client: TestClient, session: SyncSession, combined: Setup, insider, insider_token: str,
):
    """Qubit lookup: the latest dilution is preselected and its qubit concentration shown."""
    actions.dilute_pool(session, combined.a, qubit_concentration=1.25, operator_id=insider.id)
    session.commit()

    response = get(client, combined.path("lane-pools"), insider_token)

    assert response.status_code == 200, response.text
    assert 'value="A"' in response.text  # hidden dilution input of pool a
    assert 'data-raw-value="1.25"' in response.text


def test_combined_pooling_saves_reads_targets_and_pooling_table(
    client: TestClient, session: SyncSession, combined: Setup, insider, insider_token: str, media_folder: Path,
):
    actions.dilute_pool(session, combined.b, qubit_concentration=1.0, operator_id=insider.id)
    session.commit()

    response = post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined, dilutions=("Orig.", "A")), token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{combined.experiment.id}")
    assert_flash(response, "Laning Completed!", "success")
    assert all((lane.target_molarity, lane.total_volume_ul) == (3.0, 50.0) for lane in combined.lanes())
    links = combined.links()
    for lane in (1, 2):
        assert links[(lane, combined.a.id)].num_m_reads == 100.0  # 200 over two lanes
        assert links[(lane, combined.b.id)].num_m_reads == 300.0
        assert links[(lane, combined.a.id)].dilution_id is None
        assert links[(lane, combined.b.id)].dilution is not None and links[(lane, combined.b.id)].dilution.identifier == "A"

    [table] = _pooling_tables(session, combined, media_folder)
    assert sorted(table["lane"].unique()) == [1, 2]
    lane_1 = table[table["lane"] == 1].set_index("pool_id")
    assert lane_1.loc[combined.a.id, "share"] == pytest.approx(0.25)
    assert lane_1.loc[combined.a.id, "pipet"] == pytest.approx(3.0 / MOLARITY * 0.25 * 50.0)
    b_molarity = 1.0 / (SIZE * 660) * 1_000_000
    assert lane_1.loc[combined.b.id, "pipet"] == pytest.approx(3.0 / b_molarity * 0.75 * 50.0)
    session.expire_all()
    comments = session.get_one(Q.experiment.select(id=combined.experiment.id)).comments
    assert any(comment.text == "Added file for pooling ratios" for comment in comments)


@pytest.mark.parametrize("overrides", [
    {"sample_sub_forms-0-m_reads": "-5"},
    {"sample_sub_forms-0-m_reads": ""},
    {"target_molarity": "-1"},
    {"target_total_volume": ""},
], ids=["negative-reads", "missing-reads", "negative-molarity", "missing-volume"])
def test_combined_pooling_invalid_values_rerender_and_save_nothing(
    client: TestClient, combined: Setup, insider_token: str, media_folder: Path, overrides: dict,
):
    before = combined.reads()

    response = post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined) | overrides, token=insider_token)

    assert_form_invalid(response)
    assert combined.a.name in response.text  # the table is rendered again
    assert combined.reads() == before
    assert all(lane.target_molarity is None for lane in combined.lanes())


def test_combined_pooling_pool_of_another_experiment_is_404(
    client: TestClient, session: SyncSession, combined: Setup, user, insider, insider_token: str, media_folder: Path,
):
    other = Setup(session, user, insider, COMBINED)
    payload = _combined_pooling_payload(combined)
    payload["sample_sub_forms-1-pool_id"] = str(other.a.id)

    response = post_form(client, combined.path("lane-pools"), payload, token=insider_token)

    assert response.status_code == 404
    assert all(lane.target_molarity is None for lane in combined.lanes())


def test_combined_pooling_unknown_dilution_is_404(client: TestClient, combined: Setup, insider_token: str, media_folder: Path):
    response = post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined, dilutions=("Z", "Orig.")), token=insider_token)

    assert response.status_code == 404
    assert all(lane.target_molarity is None for lane in combined.lanes())


def test_wrong_variant_is_400(client: TestClient, combined: Setup, separate: Setup, insider_token: str):
    for step in ("lane-pools", "load-flow-cell", "distribute-reads"):
        assert get(client, f"{PREFIX}/{combined.experiment.id}/{step}/separate", insider_token).status_code == 400
        assert get(client, f"{PREFIX}/{separate.experiment.id}/{step}/combined", insider_token).status_code == 400


# ── Lane pooling: separate ──────────────────────────────────────────────────


def _separate_pooling_payload(setup: Setup, reads: dict[tuple[int, int], float], targets: dict[int, tuple[str, str]]) -> dict:
    payload = {}
    for i, (lane, (molarity, volume)) in enumerate(sorted(targets.items())):
        payload |= {f"lane_sub_forms-{i}-lane": str(lane), f"lane_sub_forms-{i}-target_concentration": molarity, f"lane_sub_forms-{i}-target_total_volume": volume}
    for i, ((lane, pool_id), m_reads) in enumerate(sorted(reads.items())):
        payload |= {
            f"sample_sub_forms-{i}-lane": str(lane), f"sample_sub_forms-{i}-pool_id": str(pool_id),
            f"sample_sub_forms-{i}-m_reads": str(m_reads), f"sample_sub_forms-{i}-dilution": "Orig.",
        }
    return payload


def test_separate_pooling_renders_one_tab_per_lane(client: TestClient, separate: Setup, insider_token: str):
    response = get(client, separate.path("lane-pools"), insider_token)

    assert response.status_code == 200, response.text
    assert 'id="lane-1-tab"' in response.text and 'id="lane-2-tab"' in response.text
    assert 'name="lane_sub_forms-1-target_concentration"' in response.text
    assert response.text.count(separate.a.name) == 2  # pool a on both lanes


def test_separate_pooling_saves_per_lane_reads_and_targets(
    client: TestClient, session: SyncSession, separate: Setup, insider_token: str, media_folder: Path,
):
    a, b = separate.a.id, separate.b.id
    reads = {(1, a): 10.0, (1, b): 30.0, (2, a): 50.0, (2, b): 50.0}

    response = post_form(client, separate.path("lane-pools"), _separate_pooling_payload(
        separate, reads, {1: ("3", "50"), 2: ("2", "40")},
    ), token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{separate.experiment.id}")
    assert separate.reads() == reads  # not divided by the number of lanes
    lane_1, lane_2 = separate.lanes()
    assert (lane_1.target_molarity, lane_1.total_volume_ul) == (3.0, 50.0)
    assert (lane_2.target_molarity, lane_2.total_volume_ul) == (2.0, 40.0)
    [table] = _pooling_tables(session, separate, media_folder)
    shares = table.set_index(["lane", "pool_id"])["share"]
    assert shares[(1, a)] == pytest.approx(0.25) and shares[(2, a)] == pytest.approx(0.5)
    pipet = table.set_index(["lane", "pool_id"])["pipet"]
    assert pipet[(2, b)] == pytest.approx(2.0 / MOLARITY * 0.5 * 40.0)


def test_separate_pooling_unknown_lane_is_404(client: TestClient, separate: Setup, insider_token: str, media_folder: Path):
    a, b = separate.a.id, separate.b.id
    payload = _separate_pooling_payload(separate, {(1, a): 1.0, (1, b): 1.0}, {1: ("3", "50"), 7: ("3", "50")})

    response = post_form(client, separate.path("lane-pools"), payload, token=insider_token)

    assert response.status_code == 404
    assert all(lane.target_molarity is None for lane in separate.lanes())


def test_separate_pooling_pool_not_on_lane_is_404(
    client: TestClient, session: SyncSession, separate: Setup, user, insider, insider_token: str, media_folder: Path,
):
    other = Setup(session, user, insider, SEPARATE)
    payload = _separate_pooling_payload(separate, {(1, separate.a.id): 1.0, (1, other.a.id): 1.0}, {1: ("3", "50")})

    response = post_form(client, separate.path("lane-pools"), payload, token=insider_token)

    assert response.status_code == 404
    assert all(lane.target_molarity is None for lane in separate.lanes())


def test_separate_pooling_negative_reads_rerender(client: TestClient, separate: Setup, insider_token: str, media_folder: Path):
    before = separate.reads()
    payload = _separate_pooling_payload(separate, {(1, separate.a.id): -1.0, (1, separate.b.id): 1.0}, {1: ("3", "50"), 2: ("3", "50")})

    response = post_form(client, separate.path("lane-pools"), payload, token=insider_token)

    assert_form_invalid(response)
    assert 'id="lane-1-tab"' in response.text
    assert separate.reads() == before


# ── Lane pooling table (rendered in the 'Lane Pools' checklist step) ────────


def _pooling_table_file(session: SyncSession, setup: Setup) -> models.MediaFile:
    session.expire_all()
    return session.get_one(Q.experiment.select(id=setup.experiment.id)).lane_pooling_table


def test_checklist_lane_pools_step_loads_the_latest_pooling_table(
    client: TestClient, session: SyncSession, combined: Setup, insider_token: str, media_folder: Path,
):
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    file = _pooling_table_file(session, combined)

    response = get(client, f"{PREFIX}/{combined.experiment.id}/checklist", insider_token, htmx=True)

    assert response.status_code == 200, response.text
    assert f"/htmx/experiments/{combined.experiment.id}/sample-pooling-table/{file.id}" in response.text


def test_pooling_table_renders_a_printable_table_per_lane(
    client: TestClient, session: SyncSession, separate: Setup, insider_token: str, media_folder: Path,
):
    a, b = separate.a.id, separate.b.id
    reads = {(1, a): 10.0, (1, b): 30.0, (2, a): 50.0, (2, b): 50.0}
    post_form(client, separate.path("lane-pools"), _separate_pooling_payload(
        separate, reads, {1: ("3", "50"), 2: ("2", "40")},
    ), token=insider_token)
    file = _pooling_table_file(session, separate)

    response = get(client, f"{PREFIX}/{separate.experiment.id}/sample-pooling-table/{file.id}", insider_token, htmx=True)

    assert response.status_code == 200, response.text
    assert "print_div('lane-pooling-ratios-container')" in response.text
    assert f"{separate.experiment.name} - Lane 1" in response.text
    assert f"{separate.experiment.name} - Lane 2" in response.text
    assert response.text.count(separate.a.name) == 2
    assert f"{2.0 / MOLARITY * 0.5 * 40.0:.2f}" in response.text  # pipet of pool b on lane 2
    assert f"{40.0 - 2 * 2.0 / MOLARITY * 0.5 * 40.0:.2f}" in response.text  # EB volume of lane 2


def test_pooling_table_without_lanes_renders_one_table(
    client: TestClient, session: SyncSession, combined: Setup, insider, insider_token: str, media_folder: Path,
):
    """Uploaded pooling tables without a 'lane' column (legacy experiment-wide pooling)."""
    df = pd.DataFrame({
        "pool": [combined.a.name, combined.b.name], "dilution": ["Orig.", "Orig."], "num_m_reads": [100.0, 300.0],
        "share": [0.25, 0.75], "qubit_concentration": [QUBIT, QUBIT], "avg_fragment_size": [SIZE, SIZE],
        "molarity": [MOLARITY, MOLARITY], "pipet": [1.0, 3.0], "target_molarity": [3.0, 3.0], "target_total_volume": [50.0, 50.0],
    })
    file = session.save(Q.media_file.create(
        name="pooling", uuid="00000000-0000-7000-8000-000000000001", size_bytes=1, type=C.MediaFileType.LANE_POOLING_TABLE,
        extension=".tsv", uploader_id=insider.id, experiment_id=combined.experiment.id,
    ))
    session.commit()
    os.makedirs(media_folder / C.MediaFileType.LANE_POOLING_TABLE.dir, exist_ok=True)
    df.to_csv(media_folder / file.path, sep="\t", index=False)

    response = get(client, f"{PREFIX}/{combined.experiment.id}/sample-pooling-table/{file.id}", insider_token, htmx=True)

    assert response.status_code == 200, response.text
    assert "print_div('lane-pooling-ratios-container')" in response.text
    assert combined.a.name in response.text and combined.b.name in response.text
    assert "46.0" in response.text  # EB volume: 50 - (1 + 3)


def test_pooling_table_missing_on_disk_is_404(
    client: TestClient, session: SyncSession, combined: Setup, insider_token: str, media_folder: Path,
):
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    file = _pooling_table_file(session, combined)
    os.remove(media_folder / file.path)

    response = get(client, f"{PREFIX}/{combined.experiment.id}/sample-pooling-table/{file.id}", insider_token, htmx=True)

    assert response.status_code == 404


def test_pooling_table_of_another_experiment_is_404(
    client: TestClient, session: SyncSession, combined: Setup, user, insider, insider_token: str, media_folder: Path,
):
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    file = _pooling_table_file(session, combined)
    other = Setup(session, user, insider, COMBINED)

    response = get(client, f"{PREFIX}/{other.experiment.id}/sample-pooling-table/{file.id}", insider_token, htmx=True)

    assert response.status_code == 404


def test_pooling_table_is_insider_only(
    client: TestClient, session: SyncSession, combined: Setup, insider_token: str, user_token: str, media_folder: Path,
):
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    file = _pooling_table_file(session, combined)

    response = get(client, f"{PREFIX}/{combined.experiment.id}/sample-pooling-table/{file.id}", user_token, htmx=True)

    assert response.status_code == 403


def _pooling_table_page(setup: Setup, file: models.MediaFile) -> str:
    return f"/experiments/{setup.experiment.id}/lane-pooling-table/{file.id}"


def test_file_table_links_every_pooling_table_to_its_page(
    client: TestClient, session: SyncSession, combined: Setup, insider_token: str, media_folder: Path,
):
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    old = _pooling_table_file(session, combined)
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    new = _pooling_table_file(session, combined)

    response = get(client, f"/htmx/files/render-table-page?experiment_id={combined.experiment.id}", insider_token, htmx=True)

    assert response.status_code == 200, response.text
    assert _pooling_table_page(combined, old) in response.text
    assert _pooling_table_page(combined, new) in response.text
    assert response.text.count("bi-table") == 2


def test_pooling_table_page_loads_the_table(
    client: TestClient, session: SyncSession, combined: Setup, insider_token: str, media_folder: Path,
):
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    file = _pooling_table_file(session, combined)

    response = get(client, _pooling_table_page(combined, file), insider_token)

    assert response.status_code == 200, response.text
    assert f"/htmx/experiments/{combined.experiment.id}/sample-pooling-table/{file.id}" in response.text
    assert f"/htmx/files/{file.id}/download" in response.text
    assert "A newer lane pooling table exists" not in response.text


def test_pooling_table_page_of_an_old_table_links_the_latest(
    client: TestClient, session: SyncSession, combined: Setup, insider_token: str, media_folder: Path,
):
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    old = _pooling_table_file(session, combined)
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    new = _pooling_table_file(session, combined)

    response = get(client, _pooling_table_page(combined, old), insider_token)

    assert response.status_code == 200, response.text
    assert "A newer lane pooling table exists" in response.text
    assert _pooling_table_page(combined, new) in response.text
    assert f"/sample-pooling-table/{old.id}" in response.text


def test_pooling_table_page_missing_on_disk_says_so(
    client: TestClient, session: SyncSession, combined: Setup, insider_token: str, media_folder: Path,
):
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    file = _pooling_table_file(session, combined)
    os.remove(media_folder / file.path)

    response = get(client, _pooling_table_page(combined, file), insider_token)

    assert response.status_code == 200, response.text
    assert "not found on disk" in response.text
    assert "/sample-pooling-table/" not in response.text


def test_pooling_table_page_of_another_file_type_is_404(
    client: TestClient, session: SyncSession, combined: Setup, insider, insider_token: str,
):
    file = session.save(Q.media_file.create(
        name="report", uuid="00000000-0000-7000-8000-000000000002", size_bytes=1, type=C.MediaFileType.CUSTOM,
        extension=".pdf", uploader_id=insider.id, experiment_id=combined.experiment.id,
    ))
    session.commit()

    assert get(client, _pooling_table_page(combined, file), insider_token).status_code == 404


def test_pooling_table_page_of_another_experiment_is_404(
    client: TestClient, session: SyncSession, combined: Setup, user, insider, insider_token: str, media_folder: Path,
):
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    file = _pooling_table_file(session, combined)
    other = Setup(session, user, insider, COMBINED)

    assert get(client, _pooling_table_page(other, file), insider_token).status_code == 404


def test_pooling_table_page_is_insider_only(
    client: TestClient, session: SyncSession, combined: Setup, insider_token: str, user_token: str, media_folder: Path,
):
    post_form(client, combined.path("lane-pools"), _combined_pooling_payload(combined), token=insider_token)
    file = _pooling_table_file(session, combined)

    assert get(client, _pooling_table_page(combined, file), user_token).status_code == 403


# ── Read distribution ───────────────────────────────────────────────────────


def test_combined_distribution_renders_total_reads(client: TestClient, combined: Setup, insider_token: str):
    response = get(client, combined.path("distribute-reads"), insider_token)

    assert response.status_code == 200, response.text
    assert 'value="100.0"' in response.text and 'value="300.0"' in response.text
    assert combined.a.name in response.text


def test_combined_distribution_splits_reads_over_lanes_and_skips_empty(client: TestClient, combined: Setup, insider_token: str):
    payload = {
        "pool_forms-0-pool_id": str(combined.a.id), "pool_forms-0-num_reads": "40",
        "pool_forms-1-pool_id": str(combined.b.id), "pool_forms-1-num_reads": "",
    }

    response = post_form(client, combined.path("distribute-reads"), payload, token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{combined.experiment.id}")
    reads = combined.reads()
    assert reads[(1, combined.a.id)] == reads[(2, combined.a.id)] == 20.0
    assert reads[(1, combined.b.id)] == reads[(2, combined.b.id)] == 150.0  # unchanged


@pytest.mark.parametrize("value", ["-1", "abc"])
def test_combined_distribution_invalid_reads_are_rejected(client: TestClient, combined: Setup, insider_token: str, value: str):
    before = combined.reads()

    response = post_form(client, combined.path("distribute-reads"), {
        "pool_forms-0-pool_id": str(combined.a.id), "pool_forms-0-num_reads": value,
    }, token=insider_token)

    assert_form_invalid(response)
    assert combined.reads() == before


def test_combined_distribution_pool_of_another_experiment_is_404(
    client: TestClient, session: SyncSession, combined: Setup, user, insider, insider_token: str,
):
    other = Setup(session, user, insider, COMBINED)
    before = other.reads()

    response = post_form(client, combined.path("distribute-reads"), {
        "pool_forms-0-pool_id": str(other.a.id), "pool_forms-0-num_reads": "10",
    }, token=insider_token)

    assert response.status_code == 404
    assert other.reads() == before


def _separate_reads_payload(entries: list[tuple[models.Pool, models.Lane, str]]) -> dict:
    payload = {}
    for i, (pool, lane, value) in enumerate(entries):
        payload |= {f"read_forms-{i}-pool_id": str(pool.id), f"read_forms-{i}-lane_id": str(lane.id), f"read_forms-{i}-num_m_reads": value}
    return payload


def test_separate_distribution_renders_a_cell_per_pool_and_lane(client: TestClient, separate: Setup, insider_token: str):
    response = get(client, separate.path("distribute-reads"), insider_token)

    assert response.status_code == 200, response.text
    assert 'name="read_forms-3-num_m_reads"' in response.text  # 2 pools x 2 lanes
    assert "Lane 1" in response.text and "Lane 2" in response.text


def test_separate_distribution_sets_each_lane_and_clears_empty(client: TestClient, separate: Setup, insider_token: str):
    lane_1, lane_2 = separate.lanes()
    a, b = separate.a, separate.b

    response = post_form(client, separate.path("distribute-reads"), _separate_reads_payload([
        (a, lane_1, "10"), (a, lane_2, "20"), (b, lane_1, ""), (b, lane_2, "5"),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{separate.experiment.id}")
    assert separate.reads() == {(1, a.id): 10.0, (2, a.id): 20.0, (1, b.id): None, (2, b.id): 5.0}


def test_separate_distribution_pool_not_on_lane_is_404(
    client: TestClient, session: SyncSession, separate: Setup, user, insider, insider_token: str,
):
    other = Setup(session, user, insider, SEPARATE)
    before = separate.reads()

    response = post_form(client, separate.path("distribute-reads"), _separate_reads_payload([
        (separate.a, separate.lanes()[0], "10"), (separate.a, other.lanes()[0], "10"),
    ]), token=insider_token)

    assert response.status_code == 404
    assert separate.reads() == before


def test_separate_distribution_negative_reads_are_rejected(client: TestClient, separate: Setup, insider_token: str):
    before = separate.reads()

    response = post_form(client, separate.path("distribute-reads"), _separate_reads_payload([
        (separate.a, separate.lanes()[0], "-3"),
    ]), token=insider_token)

    assert_form_invalid(response)
    assert separate.reads() == before


# ── Flow-cell loading ───────────────────────────────────────────────────────


def _qc_lanes(setup: Setup) -> None:
    """Lane QC values, so the lane molarity is known."""
    for lane in setup.lanes():
        lane.original_qubit_concentration, lane.avg_fragment_size, lane.phi_x = QUBIT, SIZE, 1.0
        setup.session.save(lane, flush=True)
    setup.session.commit()


LOAD = {"phi_x": "1.5", "target_molarity": "1.5", "total_volume_ul": "100", "measured_qubit": "0.4"}


def test_combined_loading_prefills_from_the_lanes(client: TestClient, combined: Setup, insider_token: str):
    _qc_lanes(combined)

    response = get(client, combined.path("load-flow-cell"), insider_token)

    assert response.status_code == 200, response.text
    assert f'value="{combined.experiment.workflow.volume_target_ul}"' in response.text  # default total volume
    assert f'value="{SIZE}"' in response.text


def test_combined_loading_loads_every_lane(client: TestClient, combined: Setup, insider_token: str):
    _qc_lanes(combined)

    response = post_form(client, combined.path("load-flow-cell"), LOAD, token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{combined.experiment.id}")
    for lane in combined.lanes():
        assert (lane.phi_x, lane.target_molarity, lane.total_volume_ul, lane.sequencing_qubit_concentration) == (1.5, 1.5, 100.0, 0.4)
        assert lane.library_volume_ul == pytest.approx(100.0 * 1.5 / MOLARITY)
    assert combined.status() == C.ExperimentStatus.LOADED


def test_combined_loading_display_fields_may_be_empty(client: TestClient, combined: Setup, insider_token: str):
    """The read-only display fields are posted back empty when nothing is known yet."""
    _qc_lanes(combined)
    display = {name: "" for name in ("avg_fragment_size", "qubit_concentration", "lane_molarity", "sequencing_molarity", "library_volume", "eb_volume")}

    response = post_form(client, combined.path("load-flow-cell"), LOAD | display, token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{combined.experiment.id}")


def test_combined_loading_without_target_molarity_is_not_loaded(client: TestClient, combined: Setup, insider_token: str):
    _qc_lanes(combined)

    response = post_form(client, combined.path("load-flow-cell"), LOAD | {"target_molarity": ""}, token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{combined.experiment.id}")
    assert all(lane.library_volume_ul is None and lane.phi_x == 1.5 for lane in combined.lanes())
    assert combined.status() == C.ExperimentStatus.DRAFT


@pytest.mark.parametrize("overrides", [{"phi_x": ""}, {"phi_x": "-1"}, {"total_volume_ul": "-5"}], ids=["missing-phi-x", "negative-phi-x", "negative-volume"])
def test_combined_loading_invalid_values_are_rejected(client: TestClient, combined: Setup, insider_token: str, overrides: dict):
    _qc_lanes(combined)

    response = post_form(client, combined.path("load-flow-cell"), LOAD | overrides, token=insider_token)

    assert_form_invalid(response)
    assert all(lane.target_molarity is None for lane in combined.lanes())


def _separate_load_payload(lanes: list[models.Lane], **per_lane: dict[str, str]) -> dict:
    payload = {}
    for i, lane in enumerate(lanes):
        row = {"lane_id": str(lane.id), **LOAD, **per_lane.get(str(i), {})}
        payload |= {f"fields-{i}-{key}": value for key, value in row.items()}
    return payload


def test_separate_loading_renders_a_row_per_lane(client: TestClient, separate: Setup, insider_token: str):
    _qc_lanes(separate)

    response = get(client, separate.path("load-flow-cell"), insider_token)

    assert response.status_code == 200, response.text
    assert 'name="fields-0-phi_x"' in response.text and 'name="fields-1-phi_x"' in response.text


def test_separate_loading_loads_each_lane(client: TestClient, separate: Setup, insider_token: str):
    _qc_lanes(separate)

    response = post_form(client, separate.path("load-flow-cell"), _separate_load_payload(
        separate.lanes(), **{"1": {"target_molarity": "2", "total_volume_ul": "50"}},
    ), token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{separate.experiment.id}")
    lane_1, lane_2 = separate.lanes()
    assert lane_1.library_volume_ul == pytest.approx(100.0 * 1.5 / MOLARITY)
    assert lane_2.library_volume_ul == pytest.approx(50.0 * 2.0 / MOLARITY)
    assert separate.status() == C.ExperimentStatus.LOADED


def test_separate_loading_one_lane_left_out_is_not_loaded(client: TestClient, separate: Setup, insider_token: str):
    _qc_lanes(separate)

    response = post_form(client, separate.path("load-flow-cell"), _separate_load_payload(separate.lanes()[:1]), token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{separate.experiment.id}")
    lane_1, lane_2 = separate.lanes()
    assert lane_1.library_volume_ul is not None and lane_2.library_volume_ul is None
    assert separate.status() == C.ExperimentStatus.DRAFT


def test_separate_loading_lane_of_another_experiment_is_404(
    client: TestClient, session: SyncSession, separate: Setup, user, insider, insider_token: str,
):
    other = Setup(session, user, insider, SEPARATE)
    _qc_lanes(separate)

    response = post_form(client, separate.path("load-flow-cell"), _separate_load_payload([separate.lanes()[0], other.lanes()[0]]), token=insider_token)

    assert response.status_code == 404
    assert all(lane.target_molarity is None for lane in separate.lanes() + other.lanes())


def test_separate_loading_invalid_value_rerenders_and_saves_nothing(client: TestClient, separate: Setup, insider_token: str):
    _qc_lanes(separate)

    response = post_form(client, separate.path("load-flow-cell"), _separate_load_payload(
        separate.lanes(), **{"1": {"phi_x": ""}},
    ), token=insider_token)

    assert_form_invalid(response)
    assert 'name="fields-1-phi_x"' in response.text  # the lane table is rendered again
    assert all(lane.target_molarity is None for lane in separate.lanes())


# ── Pool dilution (DilutePoolsAction) ───────────────────────────────────────


def _dilute_path(client: TestClient, setup: Setup) -> str:
    return client.app.url_path_for("DilutePoolsAction.Submit", experiment_id=str(setup.experiment.id))  # type: ignore[attr-defined]


def _dilute_payload(setup: Setup, qubits: tuple[str, str]) -> dict:
    payload = {"target_molarity": "3", "target_total_volume": "50"}
    for i, (pool, qubit) in enumerate(zip(setup.pools, qubits)):
        payload |= {f"pool_forms-{i}-pool_id": str(pool.id), f"pool_forms-{i}-qubit_after_dilution": qubit}
    return payload


def _dilutions(session: SyncSession, pool: models.Pool) -> list[tuple[str, float]]:
    session.expire_all()
    pool = session.get_one(Q.pool.select(id=pool.id))
    return [(dilution.identifier, dilution.qubit_concentration) for dilution in pool.dilutions]


def test_dilution_renders_a_row_per_pool(client: TestClient, combined: Setup, insider_token: str):
    response = get(client, _dilute_path(client, combined), insider_token)

    assert response.status_code == 200, response.text
    assert combined.a.name in response.text and combined.b.name in response.text
    assert 'name="pool_forms-1-qubit_after_dilution"' in response.text
    assert f"{MOLARITY:.2f}" in response.text


def test_dilution_adds_dilutions_only_for_filled_pools(client: TestClient, session: SyncSession, combined: Setup, insider_token: str):
    response = post_form(client, _dilute_path(client, combined), _dilute_payload(combined, ("1.5", "")), token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{combined.experiment.id}")
    assert "dilutions-tab" in response.headers["HX-Redirect"]
    assert _dilutions(session, combined.a) == [("A", 1.5)]
    assert _dilutions(session, combined.b) == []

    post_form(client, _dilute_path(client, combined), _dilute_payload(combined, ("0.5", "")), token=insider_token)
    assert _dilutions(session, combined.a) == [("A", 1.5), ("B", 0.5)]


@pytest.mark.parametrize("qubit", ["-1", "abc"])
def test_dilution_invalid_qubit_rerenders_and_saves_nothing(
    client: TestClient, session: SyncSession, combined: Setup, insider_token: str, qubit: str,
):
    response = post_form(client, _dilute_path(client, combined), _dilute_payload(combined, (qubit, "1")), token=insider_token)

    assert_form_invalid(response)
    assert combined.a.name in response.text  # the pool table is rendered again
    assert _dilutions(session, combined.a) == [] and _dilutions(session, combined.b) == []


def test_dilution_pool_of_another_experiment_is_404(
    client: TestClient, session: SyncSession, combined: Setup, user, insider, insider_token: str,
):
    other = Setup(session, user, insider, COMBINED)
    payload = _dilute_payload(combined, ("1", "1"))
    payload["pool_forms-1-pool_id"] = str(other.a.id)

    response = post_form(client, _dilute_path(client, combined), payload, token=insider_token)

    assert response.status_code == 404
    assert _dilutions(session, combined.a) == [] and _dilutions(session, other.a) == []


def test_dilution_is_insider_only(client: TestClient, session: SyncSession, combined: Setup, user_token: str):
    assert get(client, _dilute_path(client, combined), user_token).status_code == 403
    assert post_form(client, _dilute_path(client, combined), _dilute_payload(combined, ("1", "1")), token=user_token).status_code == 403
    assert _dilutions(session, combined.a) == []
