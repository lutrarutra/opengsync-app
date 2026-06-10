from opengsync_db import SyncDBHandler, queries as Q
from opengsync_db.categories import ExperimentWorkFlow

from .create_units import (
    create_user, create_seq_request, create_library, create_pool,
    create_experiment
)  # noqa


def test_experiment_lanes(db: SyncDBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    NUM_LIBRARIES = 10
    NUM_POOLS = 5
    PREV_NUM_LANES = db.session.count(Q.lane.select())

    libraries = []

    for _ in range(NUM_LIBRARIES):
        library = create_library(db, user, seq_request)
        libraries.append(library)

    pools = []

    for i in range(NUM_POOLS):
        pool = create_pool(db, user, seq_request)
        libraries[i % NUM_LIBRARIES].pool_id = pool.id
        db.session.save(libraries[i % NUM_LIBRARIES])
        pools.append(pool)

    assert seq_request is not None
    assert len(seq_request.pools) == NUM_POOLS

    for pool in pools:
        db.session.refresh(pool)
        assert pool is not None
        assert pool.num_libraries == len(pool.libraries)

    experiment = create_experiment(db, user, ExperimentWorkFlow.NOVASEQ_6K_S4_XP)

    assert ExperimentWorkFlow.NOVASEQ_6K_S4_XP.flow_cell_type.num_lanes == experiment.num_lanes
    assert experiment.num_lanes == db.session.count(Q.lane.select()) - PREV_NUM_LANES

    for pool in pools:
        db.actions.link_pool_experiment(experiment, pool)

    db.session.refresh(experiment)
    assert len(db.session.get_all(Q.experiment.select())) == db.session.count(Q.experiment.select())
    assert experiment is not None
    assert len(experiment.lanes) == experiment.num_lanes
    assert experiment.num_lanes == experiment.flowcell_type.num_lanes
    assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_6K_S4_XP.flow_cell_type.num_lanes

    empty_pool = create_pool(db, user, seq_request)
    db.actions.link_pool_experiment(experiment, empty_pool)
    lane = db.actions.add_pool_to_lane(experiment, pool=empty_pool, lane=experiment.lanes[0])
    db.session.refresh(lane)

    assert len(lane.pool_links) == 1

    db.session.refresh(experiment)
    assert experiment is not None
    assert len(experiment.pools) == NUM_POOLS + 1

    db.session.refresh(experiment)
    assert experiment is not None
    for _lane in experiment.lanes:
        if _lane.number == 1:
            assert _lane.id == lane.id
            assert len(_lane.pool_links) == 1
        else:
            assert _lane.id != lane.id
            assert len(_lane.pool_links) == 0

    lane = db.actions.remove_pool_from_lane(experiment, empty_pool, lane)
    db.session.refresh(lane)
    assert len(lane.pool_links) == 0

    db.session.refresh(experiment)
    assert experiment is not None
    assert len(experiment.pools) == NUM_POOLS + 1

    db.session.refresh(experiment)
    assert experiment is not None
    for lane in experiment.lanes:
        assert len(lane.pool_links) == 0

    for i, pool in enumerate(pools):
        db.actions.add_pool_to_lane(experiment, pool, experiment.lanes[i % experiment.num_lanes])

    counter = 0
    db.session.refresh(experiment)
    assert experiment is not None
    for lane in experiment.lanes:
        db.session.refresh(lane)
        counter += len(lane.pool_links)

    assert counter == len(pools)

    # Decrease number of lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_6K_S2_XP.id
    db.session.flush()
    db.session.save(experiment)
    db.session.refresh(experiment)
    assert db.session.count(Q.lane.select()) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_6K_S2_XP.flow_cell_type.num_lanes

    db.session.refresh(experiment)
    assert experiment is not None
    assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_6K_S2_XP
    assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_6K_S2_XP.flow_cell_type.num_lanes
    assert experiment.num_lanes == len(experiment.lanes)

    # Increase number of lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_6K_S4_XP.id
    db.session.save(experiment)
    db.session.flush()
    db.session.refresh(experiment)
    assert db.session.count(Q.lane.select()) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_6K_S4_XP.flow_cell_type.num_lanes

    db.session.refresh(experiment)
    assert experiment is not None
    assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_6K_S4_XP
    assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_6K_S4_XP.flow_cell_type.num_lanes
    assert experiment.num_lanes == len(experiment.lanes)

    # STD workflow - combined lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_6K_S4_STD.id
    db.session.save(experiment)
    db.session.flush()
    db.session.refresh(experiment)
    assert db.session.count(Q.lane.select()) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_6K_S4_STD.flow_cell_type.num_lanes
    db.session.refresh(experiment)
    assert experiment is not None
    assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_6K_S4_STD
    assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_6K_S4_STD.flow_cell_type.num_lanes

    for pool in experiment.pools:
        db.session.refresh(pool)
        assert len(pool.lane_links) == ExperimentWorkFlow.NOVASEQ_6K_S4_STD.flow_cell_type.num_lanes

    # Decrease Lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_6K_S1_STD.id
    db.session.save(experiment)

    assert db.session.count(Q.lane.select()) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_6K_S1_STD.flow_cell_type.num_lanes
    db.session.refresh(experiment)
    assert experiment is not None
    assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_6K_S1_STD
    assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_6K_S1_STD.flow_cell_type.num_lanes

    for pool in experiment.pools:
        db.session.refresh(pool)
        assert len(pool.lane_links) == ExperimentWorkFlow.NOVASEQ_6K_S1_STD.flow_cell_type.num_lanes

    # Delete experiment
    db.session.delete(experiment)
    assert db.session.count(Q.lane.select()) == PREV_NUM_LANES

    for pool in pools:
        db.session.refresh(pool)
        assert pool is not None
        assert len(pool.lane_links) == 0