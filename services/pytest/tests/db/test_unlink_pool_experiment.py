"""Unlinking a pool from an experiment (actions.unlink_pool_experiment).

Regression: the remove-pool route used to only detach the pool (Pool.experiment_id) and left its
lane links behind. The lane-based queries (barcode clashes, flowcell, lane pooling) join through
lane_pool_link, so the removed pool's libraries were still on the experiment's lanes.
"""
from opengsync_db import SyncSession, models, actions, queries as Q, categories as C

from .create_units import create_user, create_seq_request, create_library, create_pool, create_experiment

COMBINED = C.ExperimentWorkFlow.NOVASEQ_6K_S1_STD  # 2 lanes, pools go on every lane
SEPARATE = C.ExperimentWorkFlow.NOVASEQ_6K_S1_XP   # 2 lanes, pools are laned by hand


def _pool_with_library(session: SyncSession, user: models.User, seq_request: models.SeqRequest, i7: str) -> tuple[models.Pool, models.Library]:
    pool = create_pool(session, user, seq_request)
    library = create_library(session, user, seq_request)
    library.pool_id = pool.id
    session.add(Q.library_index.create(
        name_i7=None, name_i5=None, sequence_i7=i7, sequence_i5=None,
        index_kit_i7_id=None, index_kit_i5_id=None, orientation=None, library_id=library.id,
    ))
    session.flush()
    session.refresh(pool)
    return pool, library


def _lane_links(session: SyncSession, experiment_id: int) -> set[tuple[int, int]]:
    """(lane number, pool id) of the experiment's lane links."""
    session.expire_all()
    links = session.query(models.links.LanePoolLink).where(models.links.LanePoolLink.experiment_id == experiment_id).all()
    return {(link.lane_num, link.pool_id) for link in links}


def _barcode_library_ids(session: SyncSession, experiment_id: int) -> set[int]:
    df = session.get_pandas(Q.pd.experiment_barcodes(experiment_id), limit=None)
    return set(df["library_id"].tolist())


def test_unlink_combined_removes_pool_from_every_lane(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    experiment = create_experiment(session, user, COMBINED)
    kept, kept_library = _pool_with_library(session, user, seq_request, "AAAAAAAA")
    removed, removed_library = _pool_with_library(session, user, seq_request, "CCCCCCCC")
    actions.link_pool_experiment(session, experiment, kept)
    actions.link_pool_experiment(session, experiment, removed)
    session.commit()
    assert _lane_links(session, experiment.id) == {(1, kept.id), (2, kept.id), (1, removed.id), (2, removed.id)}

    actions.unlink_pool_experiment(session, experiment_id=experiment.id, pool_id=removed.id)
    session.commit()

    assert _lane_links(session, experiment.id) == {(1, kept.id), (2, kept.id)}
    assert _barcode_library_ids(session, experiment.id) == {kept_library.id}
    assert session.get_one(Q.pool.select(id=removed.id)).experiment_id is None
    assert session.get_one(Q.library.select(id=removed_library.id)).experiment_id is None
    assert session.get_one(Q.library.select(id=kept_library.id)).experiment_id == experiment.id


def test_unlink_separate_removes_pool_from_its_lanes(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    experiment = create_experiment(session, user, SEPARATE)
    kept, kept_library = _pool_with_library(session, user, seq_request, "AAAAAAAA")
    removed, _ = _pool_with_library(session, user, seq_request, "CCCCCCCC")
    actions.link_pool_experiment(session, experiment, kept)
    actions.link_pool_experiment(session, experiment, removed)
    lane_1, lane_2 = sorted(experiment.lanes, key=lambda lane: lane.number)
    actions.add_pool_to_lane(session, experiment, kept, lane_1)
    actions.add_pool_to_lane(session, experiment, removed, lane_1)
    actions.add_pool_to_lane(session, experiment, removed, lane_2)
    session.commit()

    actions.unlink_pool_experiment(session, experiment_id=experiment.id, pool_id=removed.id)
    session.commit()

    assert _lane_links(session, experiment.id) == {(1, kept.id)}
    assert _barcode_library_ids(session, experiment.id) == {kept_library.id}


def test_unlinked_pool_relinked_elsewhere_only_shows_on_new_experiment(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    old = create_experiment(session, user, COMBINED)
    new = create_experiment(session, user, COMBINED)
    pool, library = _pool_with_library(session, user, seq_request, "AAAAAAAA")
    actions.link_pool_experiment(session, old, pool)
    session.commit()

    actions.unlink_pool_experiment(session, experiment_id=old.id, pool_id=pool.id)
    session.commit()
    session.refresh(pool)
    actions.link_pool_experiment(session, new, pool)
    session.commit()

    assert _lane_links(session, old.id) == set()
    assert _barcode_library_ids(session, old.id) == set()
    assert _barcode_library_ids(session, new.id) == {library.id}
    assert session.get_one(Q.library.select(id=library.id)).experiment_id == new.id
