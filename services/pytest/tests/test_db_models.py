from opengsync_db import DBHandler, DBSession
from opengsync_db.categories import ExperimentWorkFlow, MUXType

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library, create_pool,
    create_feature, create_experiment, create_file, create_group
)  # noqa


def test_mux_links(db: DBHandler):
    user = create_user(db)
    project = create_project(db, user)
    seq_request = create_seq_request(db, user)
    library = create_library(db, user, seq_request)

    NUM_SAMPLES = 10

    for _ in range(NUM_SAMPLES):
        sample = create_sample(db, user, project)
        db.link_sample_library(
            sample.id, library.id,
            mux=dict(barcode="sequence", pattern="pattern", read="read"),
        )

    user = db.get_user(user.id)
    db.refresh(user)
    assert user is not None
    assert len(user.samples) == NUM_SAMPLES
    assert user.num_samples == NUM_SAMPLES

    project = db.get_project(project.id)
    db.refresh(project)
    assert project is not None
    assert len(project.samples) == NUM_SAMPLES

    seq_request = db.get_seq_request(seq_request.id)
    db.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == 1
    assert seq_request.num_libraries == 1

    library = db.get_library(library.id)
    db.refresh(library)
    assert library is not None
    assert len(library.sample_links) == NUM_SAMPLES
    assert library.num_samples == NUM_SAMPLES

    db.delete_library(library.id)

    user = db.get_user(user.id)
    db.refresh(user)
    assert user is not None
    assert len(user.samples) == 0
    assert user.num_samples == 0

    project = db.get_project(project.id)
    db.refresh(project)
    assert project is not None
    assert len(project.samples) == 0

    seq_request = db.get_seq_request(seq_request.id)
    db.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == 0
    assert seq_request.num_libraries == 0


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

    _ = create_seq_request(db, user_1)
    req_2 = create_seq_request(db, user_2)

    _ = create_project(db, user_1)
    p2 = create_project(db, user_2)

    req_2.group_id = group.id
    p2.group_id = group.id

    db.update_seq_request(req_2)
    db.update_project(p2)
    db.flush()

    assert len(db.get_seq_requests(user_id=user_1.id, limit=None)[0]) == 2
    assert len(db.get_seq_requests(user_id=user_2.id, limit=None)[0]) == 1
    assert len(db.get_projects(user_id=user_1.id, limit=None)[0]) == 2
    assert len(db.get_projects(user_id=user_2.id, limit=None)[0]) == 1
