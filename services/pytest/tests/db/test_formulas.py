import random
from pytest import approx
from opengsync_db import SyncSession, actions, models, categories as C, queries as Q

from .test_hybrid_properties import assert_hybrids
from .create_units import (
    create_user, create_experiment, create_pool, create_library, create_seq_request
)

def test_separate_lane_molarity(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)

    NUM_LIBRARIES = 50
    for _ in range(NUM_LIBRARIES):
        library = create_library(session, user, seq_request=seq_request)

    assert session.count(Q.library.select()) == len(session.get_all(Q.library.select(), limit=None)) == NUM_LIBRARIES

    NUM_POOLS = 6
    pools = []
    for _ in range(NUM_POOLS):
        pool = create_pool(session, user, seq_request=seq_request)
        pools.append(pool)

    libraries = session.get_all(Q.library.select(), limit=None)
    assert session.count(Q.pool.select()) == NUM_POOLS
    for i, library in enumerate(libraries):
        library.pool_id = pools[i % NUM_POOLS].id
        session.save(library)

    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    assert len(experiment.lanes) == experiment.num_lanes
    assert len(experiment.lanes) == C.ExperimentWorkFlow.NOVASEQ_6K_S4_XP.flow_cell_type.num_lanes
    assert len(session.get_all(Q.lane.select(), limit=None)) == session.count(Q.lane.select()) == experiment.num_lanes

    for i, pool in enumerate(session.get_all(Q.pool.select(), limit=None)):
        actions.link_pool_experiment(session, experiment, pool)
        actions.add_pool_to_lane(session, experiment, pool=pool, lane=experiment.lanes[i % experiment.num_lanes])

    for pool in session.get_all(Q.pool.select(), limit=None):
        pool.avg_fragment_size = random.randint(200, 500)
        pool.qubit_concentration = random.uniform(1, 10)
        session.save(pool)

    for lane in session.get_all(Q.lane.select(), limit=None):
        session.refresh(lane)
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

    session.flush()
    session.refresh(experiment)
    df = session.get_pandas(Q.pd.experiment_lanes(experiment.id), limit=None).set_index("lane")
    assert len(df) == experiment.num_lanes
    for lane in experiment.lanes:
        session.refresh(lane)
        lane_row = df.loc[lane.number]
        
        if len(lane.pool_links) == 1:
            assert lane.avg_fragment_size is not None
            assert lane_row["avg_fragment_size"] == lane.avg_fragment_size  # type: ignore
            assert lane.original_qubit_concentration is not None
            assert lane_row["original_qubit_concentration"] == approx(lane.original_qubit_concentration)  # type: ignore

            lane_molarity = lane.original_qubit_concentration / (lane.avg_fragment_size * 660) * 1_000_000
            assert lane_row["lane_molarity"] == approx(lane_molarity)  # type: ignore
            assert lane_row["molarity"] == approx(lane.molarity)  # type: ignore


    for lane in experiment.lanes:
        session.refresh(lane)
        lane.avg_fragment_size = random.randint(200, 500)
        lane.original_qubit_concentration = random.uniform(1, 10)
        lane.sequencing_qubit_concentration = random.uniform(1, 10)

    session.flush()
    session.refresh(experiment)
    for lane in experiment.lanes:
        assert lane._avg_fragment_size is not None
        assert lane._avg_fragment_size == lane.avg_fragment_size
        
        assert lane.qubit_concentration is not None
        assert lane.qubit_concentration == lane.sequencing_qubit_concentration

        assert lane._original_qubit_concentration is not None
        assert lane.original_qubit_concentration == lane._original_qubit_concentration

    session.flush()
    session.refresh(experiment)
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

    session.flush()
    session.refresh(experiment)
    df = session.get_pandas(Q.pd.experiment_lanes(experiment.id), limit=None).set_index("lane")
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
        assert row["original_molarity"] == approx(lane.original_molarity)  # type: ignore
        assert row["molarity"] == approx(lane.molarity)  # type: ignore

# Illumina: nM = ng/µL × 10^6 / (660 g/mol per bp × average size in bp)
QUBIT, SIZE, DILUTED_QUBIT = 2.0, 400, 0.4
ORIGINAL_NM = 7.575757575757576  # 2 ng/µL × 10^6 / (660 × 400 bp)
DILUTED_NM = 1.5151515151515151  # 0.4 ng/µL × 10^6 / (660 × 400 bp)


def test_molarity_matches_the_illumina_conversion(session: SyncSession):
    """Pool molarity (Python and SQL) against a hand-computed value."""
    user = create_user(session)
    pool = create_pool(session, user, create_seq_request(session, user))
    pool.qubit_concentration, pool.avg_fragment_size = QUBIT, SIZE

    assert_hybrids(session, pool, models.Pool, {"molarity": ORIGINAL_NM})


def test_pool_molarity_without_a_positive_size_is_unknown(session: SyncSession):
    user = create_user(session)
    pool = create_pool(session, user, create_seq_request(session, user))
    pool.qubit_concentration, pool.avg_fragment_size = QUBIT, 0

    assert_hybrids(session, pool, models.Pool, {"molarity": None})


def test_lane_molarity_ignores_the_sequencing_qubit(session: SyncSession):
    """The original/lane molarity (which the library volume at flow-cell loading divides by) stays the
    pre-dilution value when the diluted qubit is measured; only ``molarity`` switches to the sequencing one."""
    user = create_user(session)
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP)
    lane = experiment.lanes[0]
    lane.original_qubit_concentration, lane.avg_fragment_size = QUBIT, SIZE

    assert_hybrids(session, lane, models.Lane, {
        "original_molarity": ORIGINAL_NM,
        "lane_molarity": ORIGINAL_NM,
        "sequencing_molarity": None,
        "molarity": ORIGINAL_NM,
    })

    lane.sequencing_qubit_concentration = DILUTED_QUBIT

    assert_hybrids(session, lane, models.Lane, {
        "original_qubit_concentration": QUBIT,
        "original_molarity": ORIGINAL_NM,
        "lane_molarity": ORIGINAL_NM,
        "sequencing_molarity": DILUTED_NM,
        "molarity": DILUTED_NM,
    })
