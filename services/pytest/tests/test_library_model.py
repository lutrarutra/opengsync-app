from opengsync_db import DBHandler
from opengsync_db.categories import MUXType

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_feature
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
        db.link_sample_library(
            sample.id, library.id,
            mux=dict(barcode="sequence", pattern="pattern", read="read"),
        )
        libraries.append(library)
    
    user = db.get_user(user.id)
    assert user is not None
    assert len(user.libraries) == NUM_LIBRARIES

    seq_request = db.get_seq_request(seq_request.id)
    assert seq_request is not None
    assert len(seq_request.libraries) == NUM_LIBRARIES
    assert seq_request.num_libraries == NUM_LIBRARIES

    sample = db.get_sample(sample.id)
    assert sample is not None
    assert len(sample.library_links) == NUM_LIBRARIES
    assert sample.num_libraries == NUM_LIBRARIES

    db.delete_library(libraries[0].id)

    user = db.get_user(user.id)
    db.refresh(user)
    assert user is not None
    assert len(user.libraries) == NUM_LIBRARIES - 1

    seq_request = db.get_seq_request(seq_request.id)
    db.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == NUM_LIBRARIES - 1
    assert seq_request.num_libraries == NUM_LIBRARIES - 1

    sample = db.get_sample(sample.id)
    db.refresh(sample)
    assert sample is not None
    assert len(sample.library_links) == NUM_LIBRARIES - 1
    assert sample.num_libraries == NUM_LIBRARIES - 1

    db.delete_seq_request(seq_request.id)
    assert db.get_seq_request(seq_request.id) is None
    assert db.get_sample(sample.id) is None

    user = db.get_user(user.id)
    db.refresh(user)
    assert user is not None
    assert len(user.libraries) == 0
    assert len(user.requests) == 0

    project = db.get_project(project.id)
    db.refresh(project)
    assert project is not None
    assert len(project.samples) == 0
    assert project.num_samples == 0


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