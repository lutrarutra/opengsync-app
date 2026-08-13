from opengsync_db import SyncDBHandler, categories as C, queries as Q

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_feature, create_pool, create_experiment
)  # noqa


def test_library_links(db: SyncDBHandler):
    user = create_user(db)
    project = create_project(db, user)
    seq_request = create_seq_request(db, user)
    sample = create_sample(db, user, project)
    
    NUM_LIBRARIES = 10

    libraries = []
    for _ in range(NUM_LIBRARIES):
        library = create_library(db, user, seq_request)
        db.actions.link_sample_library(
            sample.id, library.id,
            mux=dict(barcode="sequence", pattern="pattern", read="read"),
        )
        libraries.append(library)
    
    db.session.refresh(user)
    assert user is not None
    assert len(user.libraries) == NUM_LIBRARIES

    db.session.refresh(project)
    assert len(project.samples) == 1
    assert project.num_samples == 1
    assert len(project.libraries) == NUM_LIBRARIES

    db.session.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == NUM_LIBRARIES
    assert seq_request.num_libraries == NUM_LIBRARIES

    db.session.refresh(sample)
    assert sample is not None
    assert len(sample.library_links) == NUM_LIBRARIES
    assert sample.num_libraries == NUM_LIBRARIES

    db.session.delete(libraries[0], flush=True)

    db.session.refresh(user)
    assert user is not None
    assert len(user.libraries) == NUM_LIBRARIES - 1

    db.session.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == NUM_LIBRARIES - 1
    assert seq_request.num_libraries == NUM_LIBRARIES - 1

    db.session.refresh(sample)
    assert sample is not None
    assert len(sample.library_links) == NUM_LIBRARIES - 1
    assert sample.num_libraries == NUM_LIBRARIES - 1
    assert db.session.count(Q.sample.select()) == 1

    db.session.delete(seq_request, flush=True)
    assert db.session.first(Q.seq_request.select(id=seq_request.id)) is None
    assert db.session.count(Q.library.select()) == 0
    assert db.session.count(Q.sample.select()) == 0
    assert db.session.first(Q.sample.select(id=sample.id)) is None

    db.session.refresh(user)
    assert user is not None
    assert len(user.libraries) == 0
    assert len(user.requests) == 0

    db.session.refresh(project)
    assert project is not None
    assert len(project.samples) == 0
    assert project.num_samples == 0
    assert len(project.libraries) == 0


def test_library_feature_link(db: SyncDBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    NUM_LIBRARIES = 10
    NUM_FEATURES = 10

    num_prev_features = len(db.session.get_all(Q.feature.select(), limit=None))
    num_prev_libraries = len(db.session.get_all(Q.library.select(), limit=None))

    features = []
    for _ in range(NUM_FEATURES):
        features.append(create_feature(db))

    libraries = []
    for _ in range(NUM_LIBRARIES):
        library = create_library(db, user, seq_request)
        libraries.append(library)

        for feature in features:
            db.actions.link_feature_library(feature.id, library.id)

    assert len(db.session.get_all(Q.feature.select(), limit=None)) == num_prev_features + NUM_FEATURES
    assert len(db.session.get_all(Q.library.select(), limit=None)) == num_prev_libraries + NUM_LIBRARIES
    assert len(db.session.get_all(Q.library.select(), limit=None)) == db.session.count(Q.library.select())

    db.session.delete(libraries[0], flush=True)

    assert db.session.count(Q.feature.select()) == num_prev_features + NUM_FEATURES
    assert db.session.count(Q.library.select()) == num_prev_libraries + NUM_LIBRARIES - 1

    db.session.refresh(seq_request)
    db.session.delete(seq_request)

    assert db.session.count(Q.feature.select()) == num_prev_features
    assert db.session.count(Q.library.select()) == num_prev_libraries


def test_experiment_link(db: SyncDBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    library_1 = create_library(db, user, seq_request)
    library_2 = create_library(db, user, seq_request)

    pool_1 = create_pool(db, user, seq_request=seq_request)
    pool_2 = create_pool(db, user, seq_request=seq_request)

    experiment = create_experiment(db, user, C.ExperimentWorkFlow.MISEQ_v2)

    library_1.pool_id = pool_1.id
    library_2.pool_id = pool_2.id

    assert len(experiment.libraries) == 0
    assert len(experiment.pools) == 0

    db.session.refresh(library_1)
    db.session.refresh(library_2)
    db.session.refresh(pool_1)
    db.session.refresh(pool_2)

    assert len(pool_1.libraries) == 1
    assert len(pool_2.libraries) == 1

    db.actions.link_pool_experiment(pool=pool_1,experiment=experiment)

    db.actions.link_pool_experiment(pool=pool_2, experiment=experiment)

    db.session.refresh(experiment)

    assert len(experiment.pools) == 2
    assert len(experiment.libraries) == 2

    db.actions.unlink_pool_experiment(pool_id=pool_1.id, experiment_id=experiment.id)

    db.session.refresh(experiment)

    assert len(experiment.pools) == 1
    assert len(experiment.libraries) == 1

    db.actions.unlink_pool_experiment(pool_id=pool_2.id,experiment_id=experiment.id)

    db.session.refresh(experiment)
    assert len(experiment.pools) == 0
    assert len(experiment.libraries) == 0
