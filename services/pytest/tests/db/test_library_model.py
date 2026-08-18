from opengsync_db import SyncSession, actions, categories as C, queries as Q

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_feature, create_pool, create_experiment
)  # noqa


def test_library_links(session: SyncSession):
    user = create_user(session)
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    sample = create_sample(session, user, project)
    
    NUM_LIBRARIES = 10

    libraries = []
    for _ in range(NUM_LIBRARIES):
        library = create_library(session, user, seq_request)
        actions.link_sample_library(
            session, sample.id, library.id,
            mux=dict(barcode="sequence", pattern="pattern", read="read"),
        )
        libraries.append(library)
    
    session.refresh(user)
    assert user is not None
    assert len(user.libraries) == NUM_LIBRARIES

    session.refresh(project)
    assert len(project.samples) == 1
    assert project.num_samples == 1
    assert len(project.libraries) == NUM_LIBRARIES

    session.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == NUM_LIBRARIES
    assert seq_request.num_libraries == NUM_LIBRARIES

    session.refresh(sample)
    assert sample is not None
    assert len(sample.library_links) == NUM_LIBRARIES
    assert sample.num_libraries == NUM_LIBRARIES

    session.delete(libraries[0], flush=True)

    session.refresh(user)
    assert user is not None
    assert len(user.libraries) == NUM_LIBRARIES - 1

    session.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == NUM_LIBRARIES - 1
    assert seq_request.num_libraries == NUM_LIBRARIES - 1

    session.refresh(sample)
    assert sample is not None
    assert len(sample.library_links) == NUM_LIBRARIES - 1
    assert sample.num_libraries == NUM_LIBRARIES - 1
    assert session.count(Q.sample.select()) == 1

    session.delete(seq_request, flush=True)
    assert session.first(Q.seq_request.select(id=seq_request.id)) is None
    assert session.count(Q.library.select()) == 0
    assert session.count(Q.sample.select()) == 0
    assert session.first(Q.sample.select(id=sample.id)) is None

    session.refresh(user)
    assert user is not None
    assert len(user.libraries) == 0
    assert len(user.requests) == 0

    session.refresh(project)
    assert project is not None
    assert len(project.samples) == 0
    assert project.num_samples == 0
    assert len(project.libraries) == 0


def test_library_feature_link(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)

    NUM_LIBRARIES = 10
    NUM_FEATURES = 10

    num_prev_features = len(session.get_all(Q.feature.select(), limit=None))
    num_prev_libraries = len(session.get_all(Q.library.select(), limit=None))

    features = []
    for _ in range(NUM_FEATURES):
        features.append(create_feature(session))

    libraries = []
    for _ in range(NUM_LIBRARIES):
        library = create_library(session, user, seq_request)
        libraries.append(library)

        for feature in features:
            actions.link_feature_library(session, feature.id, library.id)

    assert len(session.get_all(Q.feature.select(), limit=None)) == num_prev_features + NUM_FEATURES
    assert len(session.get_all(Q.library.select(), limit=None)) == num_prev_libraries + NUM_LIBRARIES
    assert len(session.get_all(Q.library.select(), limit=None)) == session.count(Q.library.select())

    session.delete(libraries[0], flush=True)

    assert session.count(Q.feature.select()) == num_prev_features + NUM_FEATURES
    assert session.count(Q.library.select()) == num_prev_libraries + NUM_LIBRARIES - 1

    session.refresh(seq_request)
    session.delete(seq_request)

    assert session.count(Q.feature.select()) == num_prev_features
    assert session.count(Q.library.select()) == num_prev_libraries


def test_experiment_link(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)

    library_1 = create_library(session, user, seq_request)
    library_2 = create_library(session, user, seq_request)

    pool_1 = create_pool(session, user, seq_request=seq_request)
    pool_2 = create_pool(session, user, seq_request=seq_request)

    experiment = create_experiment(session, user, C.ExperimentWorkFlow.MISEQ_v2)

    library_1.pool_id = pool_1.id
    library_2.pool_id = pool_2.id

    assert len(experiment.libraries) == 0
    assert len(experiment.pools) == 0

    session.refresh(library_1)
    session.refresh(library_2)
    session.refresh(pool_1)
    session.refresh(pool_2)

    assert len(pool_1.libraries) == 1
    assert len(pool_2.libraries) == 1

    actions.link_pool_experiment(session, pool=pool_1,experiment=experiment)

    actions.link_pool_experiment(session, pool=pool_2, experiment=experiment)

    session.refresh(experiment)

    assert len(experiment.pools) == 2
    assert len(experiment.libraries) == 2

    actions.unlink_pool_experiment(session, pool_id=pool_1.id, experiment_id=experiment.id)

    session.refresh(experiment)

    assert len(experiment.pools) == 1
    assert len(experiment.libraries) == 1

    actions.unlink_pool_experiment(session, pool_id=pool_2.id,experiment_id=experiment.id)

    session.refresh(experiment)
    assert len(experiment.pools) == 0
    assert len(experiment.libraries) == 0
