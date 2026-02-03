import random
from pytest import approx
from opengsync_db import DBHandler, categories as cats

from .create_units import (
    create_user, create_project, create_experiment, create_sample, create_pool, create_library, create_seq_request
)

def test_separate_lane_molarity(db: DBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    NUM_LIBRARIES = 50
    for _ in range(NUM_LIBRARIES):
        library = create_library(db, user, seq_request=seq_request)

    assert len(libraries := db.libraries.find(limit=None)[0]) == NUM_LIBRARIES

    NUM_POOLS = 6
    pools = []
    for _ in range(NUM_POOLS):
        pool = create_pool(db, user, seq_request=seq_request)
        pools.append(pool)

    assert len(db.pools.find(limit=None)[0]) == NUM_POOLS
    for i, library in enumerate(libraries):
        db.libraries.add_to_pool(library.id, pools[i % NUM_POOLS].id)

    experiment = create_experiment(db, user, cats.ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    assert len(experiment.lanes) == experiment.num_lanes
    assert len(experiment.lanes) == cats.ExperimentWorkFlow.NOVASEQ_6K_S4_XP.flow_cell_type.num_lanes
    assert len(db.lanes.find(limit=None)[0]) == experiment.num_lanes

    for i, pool in enumerate(db.pools.find(limit=None)[0]):
        db.links.link_pool_experiment(experiment.id, pool.id)
        db.links.add_pool_to_lane(experiment, pool=pool, lane_num=(i % experiment.num_lanes) + 1)

    for pool in db.pools.find(limit=None)[0]:
        pool.avg_fragment_size = random.randint(200, 500)
        pool.qubit_concentration = random.uniform(1, 10)
        db.pools.update(pool)

    for lane in db.lanes.find(limit=None)[0]:
        db.refresh(lane)
        assert lane._avg_fragment_size is None
        assert lane._original_qubit_concentration is None
        assert lane.sequencing_molarity is None
        if len(lane.pool_links) == 1:
            assert lane.avg_fragment_size is not None
            assert lane.avg_fragment_size == lane.pool_links[0].pool.avg_fragment_size
            assert lane.original_qubit_concentration is not None
            expected_conc = lane.pool_links[0].pool.qubit_concentration
            assert lane.original_qubit_concentration == approx(expected_conc)
        else:
            assert lane.avg_fragment_size is None
            assert lane.original_qubit_concentration is None

    db.close_session()
    db.open_session()
    experiment = db.experiments[experiment.id]
    df = db.pd.get_experiment_lanes(experiment.id).set_index("lane")
    assert len(df) == experiment.num_lanes
    for lane in experiment.lanes:
        db.refresh(lane)
        lane_row = df.loc[lane.number]
        
        if len(lane.pool_links) == 1:
            assert lane.avg_fragment_size is not None
            assert lane_row["avg_fragment_size"] == lane.avg_fragment_size  # type: ignore
            assert lane.original_qubit_concentration is not None
            assert lane_row["original_qubit_concentration"] == approx(lane.original_qubit_concentration)  # type: ignore

            lane_molarity = lane.original_qubit_concentration / (lane.avg_fragment_size * 660) * 1_000_000
            assert lane_row["lane_molarity"] == approx(lane_molarity)  # type: ignore


    for lane in experiment.lanes:
        db.refresh(lane)
        lane.avg_fragment_size = random.randint(200, 500)
        lane.original_qubit_concentration = random.uniform(1, 10)
        lane.sequencing_qubit_concentration = random.uniform(1, 10)

    db.close_session()
    db.open_session()
    experiment = db.experiments[experiment.id]
    for lane in experiment.lanes:
        assert lane._avg_fragment_size is not None
        assert lane._avg_fragment_size == lane.avg_fragment_size
        
        assert lane.qubit_concentration is not None
        assert lane.qubit_concentration == lane.sequencing_qubit_concentration

        assert lane._original_qubit_concentration is not None
        assert lane.original_qubit_concentration == lane._original_qubit_concentration


    db.close_session()
    db.open_session()
    experiment = db.experiments[experiment.id]
    for lane in experiment.lanes:
        assert lane.molarity is not None
        assert lane.molarity == lane.sequencing_molarity

        assert lane._original_qubit_concentration is not None
        assert lane._avg_fragment_size is not None
        lane_molarity = lane._original_qubit_concentration / (lane._avg_fragment_size * 660) * 1_000_000
        assert lane.original_molarity == approx(lane_molarity)

        assert lane.sequencing_qubit_concentration is not None
        seq_molarity = lane.sequencing_qubit_concentration / (lane._avg_fragment_size * 660) * 1_000_000
        assert lane.sequencing_molarity == approx(seq_molarity)


    db.close_session()
    db.open_session()
    experiment = db.experiments[experiment.id]
    df = db.pd.get_experiment_lanes(experiment.id).set_index("lane")
    for lane in experiment.lanes:
        row = df.loc[lane.number]
        assert lane.molarity is not None
        assert lane.molarity == lane.sequencing_molarity

        assert lane._original_qubit_concentration is not None
        assert lane._avg_fragment_size is not None
        lane_molarity = lane._original_qubit_concentration / (lane._avg_fragment_size * 660) * 1_000_000
        assert lane.original_molarity == approx(lane_molarity)

        assert lane.sequencing_qubit_concentration is not None
        seq_molarity = lane.sequencing_qubit_concentration / (lane._avg_fragment_size * 660) * 1_000_000
        assert lane.sequencing_molarity == approx(seq_molarity)
        assert row["lane_molarity"] == approx(lane.lane_molarity)  # type: ignore
        assert row["sequencing_molarity"] == approx(lane.sequencing_molarity)  # type: ignore