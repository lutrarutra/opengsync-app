from opengsync_db import DBHandler, categories

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_feature, create_pool, create_experiment
)  # noqa


def test_library_links(db: DBHandler):
    user = create_user(db)
    project = create_project(db, user)
    seq_request = create_seq_request(db, user)
    sample = create_sample(db, user, project)
    
    NUM_LIBRARIES = 10

    libraries = []
    for _ in range(NUM_LIBRARIES):
        library = create_library(db, user, seq_request)
        db.links.link_sample_library(
            sample.id, library.id,
            mux=dict(barcode="sequence", pattern="pattern", read="read"),
        )
        libraries.append(library)
    
    db.refresh(user)
    assert user is not None
    assert len(user.libraries) == NUM_LIBRARIES

    db.refresh(project)
    assert len(project.samples) == 1
    assert project.num_samples == 1
    assert len(project.libraries) == NUM_LIBRARIES

    db.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == NUM_LIBRARIES
    assert seq_request.num_libraries == NUM_LIBRARIES

    db.refresh(sample)
    assert sample is not None
    assert len(sample.library_links) == NUM_LIBRARIES
    assert sample.num_libraries == NUM_LIBRARIES

    db.libraries.delete(libraries[0])

    db.refresh(user)
    assert user is not None
    assert len(user.libraries) == NUM_LIBRARIES - 1

    db.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == NUM_LIBRARIES - 1
    assert seq_request.num_libraries == NUM_LIBRARIES - 1

    db.refresh(sample)
    assert sample is not None
    assert len(sample.library_links) == NUM_LIBRARIES - 1
    assert sample.num_libraries == NUM_LIBRARIES - 1
    assert len(db.samples.find(limit=None)[0]) == 1

    db.seq_requests.delete(seq_request.id)
    assert db.seq_requests.get(seq_request.id) is None
    assert len(db.libraries.find(limit=None)[0]) == 0
    assert len(db.samples.find(limit=None)[0]) == 0
    assert db.samples.get(sample.id) is None

    db.refresh(user)
    assert user is not None
    assert len(user.libraries) == 0
    assert len(user.requests) == 0

    db.refresh(project)
    assert project is not None
    assert len(project.samples) == 0
    assert project.num_samples == 0
    assert len(project.libraries) == 0


def test_library_feature_link(db: DBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    NUM_LIBRARIES = 10
    NUM_FEATURES = 10

    num_prev_features = len(db.features.find(limit=None)[0])
    num_prev_libraries = len(db.libraries.find(limit=None)[0])

    features = []
    for _ in range(NUM_FEATURES):
        features.append(create_feature(db))

    libraries = []
    for _ in range(NUM_LIBRARIES):
        library = create_library(db, user, seq_request)
        libraries.append(library)

        for feature in features:
            db.links.link_feature_library(feature.id, library.id)

    assert len(db.features.find(limit=None)[0]) == num_prev_features + NUM_FEATURES
    assert len(db.libraries.find(limit=None)[0]) == num_prev_libraries + NUM_LIBRARIES

    db.libraries.delete(libraries[0])

    assert len(db.features.find(limit=None)[0]) == num_prev_features + NUM_FEATURES
    assert len(db.libraries.find(limit=None)[0]) == num_prev_libraries + NUM_LIBRARIES - 1

    db.seq_requests.delete(seq_request.id)

    assert len(db.features.find(limit=None)[0]) == num_prev_features
    assert len(db.libraries.find(limit=None)[0]) == num_prev_libraries


def test_experiment_link(db: DBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    library_1 = create_library(db, user, seq_request)
    library_2 = create_library(db, user, seq_request)

    pool_1 = create_pool(db, user, seq_request=seq_request)
    pool_2 = create_pool(db, user, seq_request=seq_request)

    experiment = create_experiment(db, user, categories.ExperimentWorkFlow.MISEQ_v2)

    db.libraries.add_to_pool(library_id=library_1.id, pool_id=pool_1.id)
    db.libraries.add_to_pool(library_id=library_2.id, pool_id=pool_2.id)

    assert len(experiment.libraries) == 0
    assert len(experiment.pools) == 0

    db.refresh(library_1)
    db.refresh(library_2)
    db.refresh(pool_1)
    db.refresh(pool_2)

    assert len(pool_1.libraries) == 1
    assert len(pool_2.libraries) == 1

    db.links.link_pool_experiment(
        pool_id=pool_1.id,
        experiment_id=experiment.id,
    )

    db.links.link_pool_experiment(
        pool_id=pool_2.id,
        experiment_id=experiment.id,
    )

    db.refresh(experiment)

    assert len(experiment.pools) == 2
    assert len(experiment.libraries) == 2

    db.links.unlink_pool_experiment(
        pool_id=pool_1.id,
        experiment_id=experiment.id,
    )

    db.refresh(experiment)

    assert len(experiment.pools) == 1
    assert len(experiment.libraries) == 1

    db.links.unlink_pool_experiment(
        pool_id=pool_2.id,
        experiment_id=experiment.id,
    )

    db.refresh(experiment)
    assert len(experiment.pools) == 0
    assert len(experiment.libraries) == 0
