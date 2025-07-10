import os
import pytest

from limbless_db import DBHandler, DBSession
from limbless_db.categories import ExperimentWorkFlow

from .create_units import (
    create_user, create_project, create_contact, create_seq_request, create_sample, create_library, create_pool,
    create_feature, create_experiment, create_file, create_group
)  # noqa


@pytest.fixture()
def db() -> DBHandler:
    db_user = os.environ["POSTGRES_USER"]
    db_password = os.environ["POSTGRES_PASSWORD"]
    db_host = os.environ["POSTGRES_HOST"]
    db_port = os.environ["POSTGRES_PORT"]
    db_name = os.environ["POSTGRES_DB"]
    db = DBHandler()
    db.connect(user=db_user, password=db_password, host=db_host, port=db_port, db=db_name)
    db.create_tables()
    return db


def test_user_links(db: DBHandler):
    user = create_user(db)

    project = create_project(db, user)

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert user is not None

        assert len(user.projects) == 1
        assert user.projects[0].id == project.id
        assert user.num_projects == 1

    sample = create_sample(db, user, project)
    with DBSession(db) as session:
        user = session.get_user(user.id)
        project = session.get_project(project.id)
        assert user is not None
        assert project is not None

        assert len(user.samples) == 1
        assert user.samples[0].id == sample.id
        assert user.num_samples == 1
        assert len(project.samples) == 1
        assert project.samples[0].id == sample.id

    seq_request = create_seq_request(db, user)
        
    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert user is not None

        assert len(user.requests) == 1
        assert user.requests[0].id == seq_request.id
        assert user.num_seq_requests == 1

    library = create_library(db, user, seq_request)
    with DBSession(db) as session:
        user = session.get_user(user.id)
        seq_request = session.get_seq_request(seq_request.id)
        assert user is not None
        assert seq_request is not None

        assert len(user.libraries) == 1
        assert user.libraries[0].id == library.id
        assert len(seq_request.libraries) == 1
        assert seq_request.libraries[0].id == library.id
        assert seq_request.num_libraries == 1

    db.link_sample_library(sample.id, library.id)

    with DBSession(db) as session:
        sample = session.get_sample(sample.id)
        library = session.get_library(library.id)
        assert sample is not None
        assert library is not None

        assert sample.num_libraries == 1
        assert len(sample.library_links) == 1
        assert sample.library_links[0].library_id == library.id
        assert library.num_samples == 1
        assert len(library.sample_links) == 1
        assert library.sample_links[0].sample_id == sample.id

    pool = create_pool(db, user, seq_request)

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert user is not None
        assert user.num_pools == 1
        assert len(user.pools) == 1

        seq_request = session.get_seq_request(seq_request.id)
        assert seq_request is not None
        assert len(seq_request.pools) == 1
        assert seq_request.pools[0].id == pool.id

    db.pool_library(library.id, pool.id)

    with DBSession(db) as session:
        library = session.get_library(library.id)
        pool = session.get_pool(pool.id)
        seq_request = session.get_seq_request(seq_request.id)
        assert library is not None
        assert pool is not None
        assert seq_request is not None

        assert pool.num_libraries == 1
        assert len(pool.libraries) == 1
        assert pool.id == library.pool_id
        assert len(seq_request.pools) == 1
        assert seq_request.pools[0].id == pool.id

    db.delete_library(library.id)
    libraries, _ = db.get_libraries(limit=None)
    assert len(libraries) == 0
    samples, _ = db.get_samples(limit=None)
    assert len(samples) == 0
    pools, _ = db.get_pools(limit=None)
    assert len(pools) == 0

    with DBSession(db) as session:
        seq_request = session.get_seq_request(seq_request.id)
        assert seq_request is not None
        assert seq_request.num_libraries == 0
        assert len(seq_request.libraries) == 0
        
        project = session.get_project(project.id)
        assert project is not None
        assert project.num_samples == 0
        assert len(project.samples) == 0
        
        user = session.get_user(user.id)
        assert user is not None
        assert user.num_seq_requests == 1
        assert len(user.requests) == 1
        assert user.num_projects == 1
        assert len(user.projects) == 1
        assert user.num_samples == 0
        assert len(user.samples) == 0
        assert user.num_pools == 0
        assert len(user.pools) == 0

    db.delete_seq_request(seq_request.id)
    seq_requests, _ = db.get_seq_requests(limit=None)
    assert len(seq_requests) == 0

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert user is not None
        assert user.num_seq_requests == 0
        assert len(user.requests) == 0


def test_library_links(db: DBHandler):
    user = create_user(db)
    project = create_project(db, user)
    seq_request = create_seq_request(db, user)
    sample = create_sample(db, user, project)
    
    NUM_LIBRARIES = 10

    libraries = []
    for _ in range(NUM_LIBRARIES):
        library = create_library(db, user, seq_request)
        db.link_sample_library(sample.id, library.id, cmo_sequence="sequence", cmo_pattern="pattern", cmo_read="read")
        libraries.append(library)
    
    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert user is not None
        assert len(user.libraries) == NUM_LIBRARIES

        seq_request = session.get_seq_request(seq_request.id)
        assert seq_request is not None
        assert len(seq_request.libraries) == NUM_LIBRARIES
        assert seq_request.num_libraries == NUM_LIBRARIES

        sample = session.get_sample(sample.id)
        assert sample is not None
        assert len(sample.library_links) == NUM_LIBRARIES
        assert sample.num_libraries == NUM_LIBRARIES

    db.delete_library(libraries[0].id)

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert user is not None
        assert len(user.libraries) == NUM_LIBRARIES - 1

        seq_request = session.get_seq_request(seq_request.id)
        assert seq_request is not None
        assert len(seq_request.libraries) == NUM_LIBRARIES - 1
        assert seq_request.num_libraries == NUM_LIBRARIES - 1

        sample = session.get_sample(sample.id)
        assert sample is not None
        assert len(sample.library_links) == NUM_LIBRARIES - 1
        assert sample.num_libraries == NUM_LIBRARIES - 1

    db.delete_seq_request(seq_request.id)

    assert db.get_seq_request(seq_request.id) is None

    assert db.get_sample(sample.id) is None

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert user is not None
        assert len(user.libraries) == 0
        assert len(user.requests) == 0

        project = session.get_project(project.id)
        assert project is not None
        assert len(project.samples) == 0
        assert project.num_samples == 0


def test_cmos_links(db: DBHandler):
    user = create_user(db)
    project = create_project(db, user)
    seq_request = create_seq_request(db, user)
    library = create_library(db, user, seq_request)

    NUM_SAMPLES = 10

    for _ in range(NUM_SAMPLES):
        sample = create_sample(db, user, project)
        db.link_sample_library(sample.id, library.id, cmo_sequence="sequence", cmo_pattern="pattern", cmo_read="read")

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert user is not None
        assert len(user.samples) == NUM_SAMPLES
        assert user.num_samples == NUM_SAMPLES

        project = session.get_project(project.id)
        assert project is not None
        assert len(project.samples) == NUM_SAMPLES

        seq_request = session.get_seq_request(seq_request.id)
        assert seq_request is not None
        assert len(seq_request.libraries) == 1
        assert seq_request.num_libraries == 1

        library = session.get_library(library.id)
        assert library is not None
        assert len(library.sample_links) == NUM_SAMPLES
        assert library.num_samples == NUM_SAMPLES

    db.delete_library(library.id)

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert user is not None
        assert len(user.samples) == 0
        assert user.num_samples == 0

        project = session.get_project(project.id)
        assert project is not None
        assert len(project.samples) == 0

        seq_request = session.get_seq_request(seq_request.id)
        assert seq_request is not None
        assert len(seq_request.libraries) == 0
        assert seq_request.num_libraries == 0


def test_library_feature_link(db: DBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    NUM_LIBRARIES = 10
    NUM_FEATURES = 10

    num_prev_features = len(db.get_features(limit=None)[0])
    num_prev_libraries = len(db.get_libraries(limit=None)[0])
    
    features = []
    for _ in range(NUM_FEATURES):
        features.append(create_feature(db))

    libraries = []
    for _ in range(NUM_LIBRARIES):
        library = create_library(db, user, seq_request)
        libraries.append(library)

        for feature in features:
            db.link_feature_library(feature.id, library.id)

    assert len(db.get_features(limit=None)[0]) == num_prev_features + NUM_FEATURES
    assert len(db.get_libraries(limit=None)[0]) == num_prev_libraries + NUM_LIBRARIES

    db.delete_library(libraries[0].id)

    assert len(db.get_features(limit=None)[0]) == num_prev_features + NUM_FEATURES
    assert len(db.get_libraries(limit=None)[0]) == num_prev_libraries + NUM_LIBRARIES - 1

    db.delete_seq_request(seq_request.id)

    assert len(db.get_features(limit=None)[0]) == num_prev_features
    assert len(db.get_libraries(limit=None)[0]) == num_prev_libraries


def test_experiment_lanes(db: DBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    NUM_LIBRARIES = 10
    NUM_POOLS = 5
    PREV_NUM_LANES = len(db.get_lanes(limit=None)[0])

    libraries = []

    for _ in range(NUM_LIBRARIES):
        library = create_library(db, user, seq_request)
        libraries.append(library)

    pools = []

    for i in range(NUM_POOLS):
        pool = create_pool(db, user, seq_request)
        db.pool_library(libraries[i % NUM_LIBRARIES].id, pool.id)
        pools.append(pool)

    with DBSession(db) as session:
        seq_request = session.get_seq_request(seq_request.id)
        assert seq_request is not None
        assert len(seq_request.pools) == NUM_POOLS
        
        for pool in pools:
            pool = db.get_pool(pool.id)
            assert pool is not None
            assert pool.num_libraries == len(pool.libraries)

    experiment = create_experiment(db, user, ExperimentWorkFlow.NOVASEQ_S4_XP)

    assert ExperimentWorkFlow.NOVASEQ_S4_XP.flow_cell_type.num_lanes == experiment.num_lanes
    assert experiment.num_lanes == len(db.get_lanes(limit=None)[0]) - PREV_NUM_LANES

    for pool in pools:
        db.link_pool_experiment(experiment.id, pool.id)

    with DBSession(db) as session:
        experiment = session.get_experiment(experiment.id)
        assert experiment is not None
        assert len(experiment.lanes) == experiment.num_lanes
        assert experiment.num_lanes == experiment.flowcell_type.num_lanes
        assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_S4_XP.flow_cell_type.num_lanes

    empty_pool = create_pool(db, user, seq_request)
    db.link_pool_experiment(experiment.id, empty_pool.id)
    lane = db.add_pool_to_lane(experiment.id, pool_id=empty_pool.id, lane_num=1)

    with DBSession(db) as session:
        experiment = session.get_experiment(experiment.id)
        assert experiment is not None
        assert len(experiment.pools) == NUM_POOLS + 1

        experiment = session.get_experiment(experiment.id)
        assert experiment is not None
        for _lane in experiment.lanes:
            if _lane.number == 1:
                assert _lane.id == lane.id
                assert len(_lane.pool_links) == 1
            else:
                assert _lane.id != lane.id
                assert len(_lane.pool_links) == 0

    lane = db.remove_pool_from_lane(experiment.id, empty_pool.id, 1)

    with DBSession(db) as session:
        experiment = session.get_experiment(experiment.id)
        assert experiment is not None
        assert len(experiment.pools) == NUM_POOLS + 1

        experiment = session.get_experiment(experiment.id)
        assert experiment is not None
        for lane in experiment.lanes:
            assert len(lane.pool_links) == 0

    for i, pool in enumerate(pools):
        db.add_pool_to_lane(experiment.id, pool.id, (i % experiment.num_lanes) + 1)

    with DBSession(db) as session:
        counter = 0
        experiment = session.get_experiment(experiment.id)
        assert experiment is not None
        for lane in experiment.lanes:
            counter += len(lane.pool_links)

        assert counter == NUM_POOLS

    # Decrease number of lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_S2_XP.id
    experiment = db.update_experiment(experiment)
    
    assert len(db.get_lanes(limit=None)[0]) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_S2_XP.flow_cell_type.num_lanes

    with DBSession(db) as session:
        experiment = session.get_experiment(experiment.id)
        assert experiment is not None
        assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_S2_XP
        assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_S2_XP.flow_cell_type.num_lanes
        assert experiment.num_lanes == len(experiment.lanes)

    # Increase number of lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_S4_XP.id
    experiment = db.update_experiment(experiment)
    assert len(db.get_lanes(limit=None)[0]) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_S4_XP.flow_cell_type.num_lanes

    with DBSession(db) as session:
        experiment = session.get_experiment(experiment.id)
        assert experiment is not None
        assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_S4_XP
        assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_S4_XP.flow_cell_type.num_lanes
        assert experiment.num_lanes == len(experiment.lanes)

    # STD workflow - combined lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_S4_STD.id
    experiment = db.update_experiment(experiment)
    assert len(db.get_lanes(limit=None)[0]) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_S4_STD.flow_cell_type.num_lanes
    with DBSession(db) as session:
        experiment = session.get_experiment(experiment.id)
        assert experiment is not None
        assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_S4_STD
        assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_S4_STD.flow_cell_type.num_lanes

        for pool in experiment.pools:
            assert len(pool.lane_links) == ExperimentWorkFlow.NOVASEQ_S4_STD.flow_cell_type.num_lanes

    # Decrease Lanes
    experiment.workflow_id = ExperimentWorkFlow.NOVASEQ_S1_STD.id
    experiment = db.update_experiment(experiment)
    
    assert len(db.get_lanes(limit=None)[0]) == PREV_NUM_LANES + ExperimentWorkFlow.NOVASEQ_S1_STD.flow_cell_type.num_lanes
    with DBSession(db) as session:
        experiment = session.get_experiment(experiment.id)
        assert experiment is not None
        assert experiment.workflow == ExperimentWorkFlow.NOVASEQ_S1_STD
        assert experiment.num_lanes == ExperimentWorkFlow.NOVASEQ_S1_STD.flow_cell_type.num_lanes

        for pool in experiment.pools:
            assert len(pool.lane_links) == ExperimentWorkFlow.NOVASEQ_S1_STD.flow_cell_type.num_lanes

    # Delete experiment
    db.delete_experiment(experiment.id)
    assert len(db.get_lanes(limit=None)[0]) == PREV_NUM_LANES

    with DBSession(db) as session:
        for pool in pools:
            pool = session.get_pool(pool.id)
            assert pool is not None
            assert len(pool.lane_links) == 0


def test_files(db: DBHandler):
    seq_request = create_seq_request(db, create_user(db))
    NUM_FILES = len(db.get_files())
    file = create_file(db, seq_request=seq_request)
    assert len(db.get_files()) == NUM_FILES + 1
    create_file(db, seq_request=seq_request)
    create_file(db, seq_request=seq_request)
    assert len(db.get_files()) == NUM_FILES + 3
    db.delete_file(file.id)
    assert len(db.get_files()) == NUM_FILES + 2
    db.delete_seq_request(seq_request.id)
    assert len(db.get_files()) == NUM_FILES


def test_group_affiliations(db: DBHandler):
    user_1 = create_user(db)
    user_2 = create_user(db)

    group = create_group(db, user_1)

    with DBSession(db) as _:
        req_1 = create_seq_request(db, user_1)
        req_2 = create_seq_request(db, user_2)

        p1 = create_project(db, user_1)
        p2 = create_project(db, user_2)

        req_2.group_id = group.id
        p2.group_id = group.id

        db.update_seq_request(req_2)
        db.update_project(p2)

    assert len(db.get_seq_requests(user_id=user_1.id, limit=None)[0]) == 2
    assert len(db.get_seq_requests(user_id=user_2.id, limit=None)[0]) == 1
    assert len(db.get_projects(user_id=user_1.id, limit=None)[0]) == 2
    assert len(db.get_projects(user_id=user_2.id, limit=None)[0]) == 1

