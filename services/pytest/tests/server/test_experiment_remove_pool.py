"""DELETE /htmx/experiments/{id}/remove-pool/{pool_id}.

Regression: the route only detached the pool (Pool.experiment_id) and left its lane links, so the
removed pool's libraries were still listed in the experiment's barcode clash check (which joins
lane -> lane_pool_link -> pool -> library) and kept their library.experiment_id.
"""
import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, actions, queries as Q, categories as C

from ..db.create_units import create_experiment, create_library, create_pool, create_seq_request
from ._http import assert_flash, delete, get

PREFIX = "/htmx/experiments"
CLASHES = "/htmx/actions/"
COMBINED = C.ExperimentWorkFlow.NOVASEQ_6K_S1_STD  # 2 lanes, pools go on every lane
SEPARATE = C.ExperimentWorkFlow.NOVASEQ_6K_S1_XP   # 2 lanes, pools are laned by hand


class Setup:
    """An experiment with two pools on both lanes, one library each, with the same barcode."""

    def __init__(self, session: SyncSession, user: models.User, insider: models.User, workflow: C.ExperimentWorkFlow):
        self.session = session
        self.experiment = create_experiment(session, insider, workflow)
        seq_request = create_seq_request(session, user)
        self.pools: list[models.Pool] = []
        self.libraries: list[models.Library] = []
        for i in range(2):
            pool = create_pool(session, user, seq_request)
            library = create_library(session, user, seq_request)
            library.name = f"Remove_Pool_Lib_{i}"
            library.pool_id = pool.id
            session.add(Q.library_index.create(
                name_i7=None, name_i5=None, sequence_i7="AAAAAAAA", sequence_i5="CCCCCCCC",
                index_kit_i7_id=None, index_kit_i5_id=None, orientation=None, library_id=library.id,
            ))
            session.flush()
            session.refresh(pool)
            actions.link_pool_experiment(session, self.experiment, pool)
            if not workflow.combined_lanes:
                for lane in self.experiment.lanes:
                    actions.add_pool_to_lane(session, self.experiment, pool, lane)
            self.pools.append(pool)
            self.libraries.append(library)
        session.commit()

    def lane_pool_ids(self) -> set[int]:
        self.session.expire_all()
        links = self.session.query(models.links.LanePoolLink).where(models.links.LanePoolLink.experiment_id == self.experiment.id).all()
        return {link.pool_id for link in links}


@pytest.fixture(params=[COMBINED, SEPARATE], ids=["combined", "separate"])
def setup(request, session: SyncSession, user, insider) -> Setup:
    return Setup(session, user, insider, request.param)


def test_remove_pool_drops_its_lane_links(client: TestClient, setup: Setup, insider_token: str):
    kept, removed = setup.pools

    response = delete(client, f"{PREFIX}/{setup.experiment.id}/remove-pool/{removed.id}", insider_token, htmx=True)

    assert response.status_code == 204, response.text
    assert_flash(response, f"Pool '{removed.name}' removed from Experiment", "success")
    assert setup.lane_pool_ids() == {kept.id}
    assert setup.session.get_one(Q.pool.select(id=removed.id)).experiment_id is None


def test_remove_pool_clears_library_experiment(client: TestClient, setup: Setup, insider_token: str):
    kept_library, removed_library = setup.libraries

    delete(client, f"{PREFIX}/{setup.experiment.id}/remove-pool/{setup.pools[1].id}", insider_token, htmx=True)

    setup.session.expire_all()
    assert setup.session.get_one(Q.library.select(id=removed_library.id)).experiment_id is None
    assert setup.session.get_one(Q.library.select(id=kept_library.id)).experiment_id == setup.experiment.id


def test_removed_pool_libraries_leave_barcode_clash_check(client: TestClient, setup: Setup, insider_token: str):
    kept_library, removed_library = setup.libraries
    before = get(client, CLASHES, insider_token, params={"experiment_id": setup.experiment.id})
    assert removed_library.name in before.text
    assert "Hamming distance of 0" in before.text

    delete(client, f"{PREFIX}/{setup.experiment.id}/remove-pool/{setup.pools[1].id}", insider_token, htmx=True)
    after = get(client, CLASHES, insider_token, params={"experiment_id": setup.experiment.id})

    assert after.status_code == 200, after.text
    assert kept_library.name in after.text
    assert removed_library.name not in after.text
    assert "Hamming distance of 0" not in after.text
