import os
import pytest

from limbless_db import DBHandler, DBSession
from limbless_db import exceptions

from .create_units import (
    create_user, create_project, create_contact, create_seq_request, create_sample, create_library, create_pool,
    create_cmo, create_feature
)


@pytest.fixture()
def db() -> DBHandler:
    db_user = os.environ["POSTGRES_USER"]
    db_password = os.environ["POSTGRES_PASSWORD"]
    db_host = os.environ["POSTGRES_HOST"]
    db_port = os.environ["POSTGRES_PORT"]
    db_name = os.environ["POSTGRES_DB"]
    db = DBHandler(user=db_user, password=db_password, host=db_host, port=db_port, db=db_name)
    db.create_tables()
    return db


def test_user_links(db: DBHandler):
    user = create_user(db)

    project = create_project(db, user)

    with DBSession(db) as session:
        user = session.get_user(user.id)

        assert len(user.projects) == 1
        assert user.projects[0].id == project.id
        assert user.num_projects == 1

    sample = create_sample(db, user, project)
    with DBSession(db) as session:
        user = session.get_user(user.id)
        project = session.get_project(project.id)

        assert len(user.samples) == 1
        assert user.samples[0].id == sample.id
        assert user.num_samples == 1
        assert len(project.samples) == 1
        assert project.samples[0].id == sample.id

    seq_request = create_seq_request(db, user)
        
    with DBSession(db) as session:
        user = session.get_user(user.id)

        assert len(user.requests) == 1
        assert user.requests[0].id == seq_request.id
        assert user.num_seq_requests == 1

    library = create_library(db, user, seq_request)
    with DBSession(db) as session:
        user = session.get_user(user.id)
        seq_request = session.get_seq_request(seq_request.id)

        assert len(user.libraries) == 1
        assert user.libraries[0].id == library.id
        assert len(seq_request.libraries) == 1
        assert seq_request.libraries[0].id == library.id
        assert seq_request.num_libraries == 1

    db.link_sample_library(sample.id, library.id)

    with DBSession(db) as session:
        sample = session.get_sample(sample.id)
        library = session.get_library(library.id)

        assert sample.num_libraries == 1
        assert len(sample.library_links) == 1
        assert sample.library_links[0].library_id == library.id
        assert library.num_samples == 1
        assert len(library.sample_links) == 1
        assert library.sample_links[0].sample_id == sample.id

    pool = create_pool(db, user, seq_request)

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert user.num_pools == 1
        assert len(user.pools) == 1

        seq_request = session.get_seq_request(seq_request.id)
        assert len(seq_request.pools) == 1
        assert seq_request.pools[0].id == pool.id

    db.link_library_pool(library.id, pool.id)

    with DBSession(db) as session:
        library = session.get_library(library.id)
        pool = session.get_pool(pool.id)
        seq_request = session.get_seq_request(seq_request.id)

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
        assert seq_request.num_libraries == 0
        assert len(seq_request.libraries) == 0
        project = session.get_project(project.id)
        assert project.num_samples == 0
        assert len(project.samples) == 0
        user = session.get_user(user.id)
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
        cmo = create_cmo(db)
        db.link_sample_library(sample.id, library.id, cmo_id=cmo.id)
        libraries.append(library)
    
    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert len(user.libraries) == NUM_LIBRARIES

        seq_request = session.get_seq_request(seq_request.id)
        assert len(seq_request.libraries) == NUM_LIBRARIES
        assert seq_request.num_libraries == NUM_LIBRARIES

        sample = session.get_sample(sample.id)
        assert len(sample.library_links) == NUM_LIBRARIES
        assert sample.num_libraries == NUM_LIBRARIES

    db.delete_library(libraries[0].id)

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert len(user.libraries) == NUM_LIBRARIES - 1

        seq_request = session.get_seq_request(seq_request.id)
        assert len(seq_request.libraries) == NUM_LIBRARIES - 1
        assert seq_request.num_libraries == NUM_LIBRARIES - 1

        sample = session.get_sample(sample.id)
        assert len(sample.library_links) == NUM_LIBRARIES - 1
        assert sample.num_libraries == NUM_LIBRARIES - 1

    db.delete_seq_request(seq_request.id)

    with pytest.raises(exceptions.ElementDoesNotExist):
        db.get_seq_request(seq_request.id)

    with pytest.raises(exceptions.ElementDoesNotExist):
        db.get_sample(sample.id)

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert len(user.libraries) == 0
        assert len(user.requests) == 0

        project = session.get_project(project.id)
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
        cmo = create_cmo(db)
        db.link_sample_library(sample.id, library.id, cmo_id=cmo.id)

    with DBSession(db) as session:
        user = session.get_user(user.id)
        assert len(user.samples) == NUM_SAMPLES
        assert user.num_samples == NUM_SAMPLES

        project = session.get_project(project.id)
        assert len(project.samples) == NUM_SAMPLES

        seq_request = session.get_seq_request(seq_request.id)
        assert len(seq_request.libraries) == 1
        assert seq_request.num_libraries == 1

        library = session.get_library(library.id)
        assert len(library.sample_links) == NUM_SAMPLES
        assert library.num_samples == NUM_SAMPLES

    num_cmos = len(db.get_cmos(limit=None)[0])
    db.delete_library(library.id)

    assert len(db.get_samples(limit=None)[0]) == num_cmos - NUM_SAMPLES


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
