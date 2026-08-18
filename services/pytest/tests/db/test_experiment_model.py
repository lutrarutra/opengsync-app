from opengsync_db import SyncSession, actions, queries as Q
from opengsync_db.categories import ExperimentWorkFlow

from .create_units import (
    create_user, create_seq_request, create_library, create_pool,
    create_experiment
)  # noqa


def test_experiment_lanes(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)

    NUM_LIBRARIES = 10
    NUM_POOLS = 5
    PREV_NUM_LANES = session.count(Q.lane.select())

    libraries = []

    for _ in range(NUM_LIBRARIES):
        library = create_library(session, user, seq_request)
        libraries.append(library)

    pools = []

    for i in range(NUM_POOLS):
        pool = create_pool(session, user, seq_request)
        libraries[i % NUM_LIBRARIES].pool_id = pool.id
        session.save(libraries[i % NUM_LIBRARIES])
        pools.append(pool)

    assert seq_request is not None
    assert len(seq_request.pools) == NUM_POOLS

    for pool in pools:
        session.refresh(pool)
        assert pool is not None
        assert pool.num_libraries == len(pool.libraries)

    experiment = create_experiment(session, user, ExperimentWorkFlow.NOVASEQ_6K_S4_XP)

    assert ExperimentWorkFlow.NOVASEQ_6K_S4_XP.flow_cell_type.num_lanes == experiment.num_lanes
    assert experiment.num_lanes == session.count(Q.lane.select()) - PREV_NUM_LANES

    for pool in pools:
        actions.link_pool_experiment(session, experiment, pool)

    session.refresh(experiment)
    assert len(session.get_all(Q.experiment.select())) == session.count(Q.experiment.select())
    assert experiment is not None
    assert len(experiment.lanes) == experiment.num_lanes
    assert experiment.num_lanes == experiment.flowcell_type.num_lanes
    assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_6K_S4_XP.flow_cell_type.num_lanes

    empty_pool = create_pool(session, user, seq_request)
    actions.link_pool_experiment(session, experiment, empty_pool)
    lane = actions.add_pool_to_lane(session, experiment, pool=empty_pool, lane=experiment.lanes[0])
    session.refresh(lane)

    assert len(lane.pool_links) == 1

    session.refresh(experiment)
    assert experiment is not None
    assert len(experiment.pools) == NUM_POOLS + 1

    session.refresh(experiment)
    assert experiment is not None
    for _lane in experiment.lanes:
        if _lane.number == 1:
            assert _lane.id == lane.id
            assert len(_lane.pool_links) == 1
        else:
            assert _lane.id != lane.id
            assert len(_lane.pool_links) == 0

    lane = actions.remove_pool_from_lane(session, experiment, empty_pool, lane)
    session.refresh(lane)
    assert len(lane.pool_links) == 0

    session.refresh(experiment)
    assert experiment is not None
    assert len(experiment.pools) == NUM_POOLS + 1

    session.refresh(experiment)
    assert experiment is not None
    for lane in experiment.lanes:
        assert len(lane.pool_links) == 0

    for i, pool in enumerate(pools):
        actions.add_pool_to_lane(session, experiment, pool, experiment.lanes[i % experiment.num_lanes])

    counter = 0
    session.refresh(experiment)
    assert experiment is not None
    for lane in experiment.lanes:
        session.refresh(lane)
        counter += len(lane.pool_links)

    assert counter == len(pools)

    # Decrease number of lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_6K_S2_XP.id
    session.flush()
    session.save(experiment)
    session.refresh(experiment)
    assert session.count(Q.lane.select()) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_6K_S2_XP.flow_cell_type.num_lanes

    session.refresh(experiment)
    assert experiment is not None
    assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_6K_S2_XP
    assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_6K_S2_XP.flow_cell_type.num_lanes
    assert experiment.num_lanes == len(experiment.lanes)

    # Increase number of lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_6K_S4_XP.id
    session.save(experiment)
    session.flush()
    session.refresh(experiment)
    assert session.count(Q.lane.select()) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_6K_S4_XP.flow_cell_type.num_lanes

    session.refresh(experiment)
    assert experiment is not None
    assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_6K_S4_XP
    assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_6K_S4_XP.flow_cell_type.num_lanes
    assert experiment.num_lanes == len(experiment.lanes)

    # STD workflow - combined lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_6K_S4_STD.id
    session.save(experiment)
    session.flush()
    session.refresh(experiment)
    assert session.count(Q.lane.select()) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_6K_S4_STD.flow_cell_type.num_lanes
    session.refresh(experiment)
    assert experiment is not None
    assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_6K_S4_STD
    assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_6K_S4_STD.flow_cell_type.num_lanes

    for pool in experiment.pools:
        session.refresh(pool)
        assert len(pool.lane_links) == ExperimentWorkFlow.NOVASEQ_6K_S4_STD.flow_cell_type.num_lanes

    # Decrease Lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_6K_S1_STD.id
    session.save(experiment)

    assert session.count(Q.lane.select()) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_6K_S1_STD.flow_cell_type.num_lanes
    session.refresh(experiment)
    assert experiment is not None
    assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_6K_S1_STD
    assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_6K_S1_STD.flow_cell_type.num_lanes

    for pool in experiment.pools:
        session.refresh(pool)
        assert len(pool.lane_links) == ExperimentWorkFlow.NOVASEQ_6K_S1_STD.flow_cell_type.num_lanes

    # Delete experiment
    session.delete(experiment)
    assert session.count(Q.lane.select()) == PREV_NUM_LANES

    for pool in pools:
        session.refresh(pool)
        assert pool is not None
        assert len(pool.lane_links) == 0