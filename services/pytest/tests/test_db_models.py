from opengsync_db import DBHandler

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_file, create_group, create_pool
)  # noqa


def test_mux_links(db: DBHandler):
    user = create_user(db)
    project = create_project(db, user)
    seq_request = create_seq_request(db, user)
    library = create_library(db, user, seq_request)

    NUM_SAMPLES = 10

    for _ in range(NUM_SAMPLES):
        sample = create_sample(db, user, project)
        db.links.link_sample_library(
            sample.id, library.id,
            mux=dict(barcode="sequence", pattern="pattern", read="read"),
        )

    user = db.users.get(user.id)
    db.refresh(user)
    assert user is not None
    assert len(user.samples) == NUM_SAMPLES
    assert user.num_samples == NUM_SAMPLES
    assert len(db.seq_requests.find(limit=None)[0]) == len(list(db.seq_requests)) == len(db.seq_requests)
    assert len(db.projects.find(limit=None)[0]) == len(list(db.projects)) == len(db.projects)

    project = db.projects.get(project.id)
    db.refresh(project)
    assert project is not None
    assert len(project.samples) == NUM_SAMPLES

    seq_request = db.seq_requests.get(seq_request.id)
    db.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == 1
    assert seq_request.num_libraries == 1

    library = db.libraries.get(library.id)
    db.refresh(library)
    assert library is not None
    assert len(library.sample_links) == NUM_SAMPLES
    assert library.num_samples == NUM_SAMPLES

    db.libraries.delete(library)

    user = db.users.get(user.id)
    db.refresh(user)
    assert user is not None
    assert len(user.samples) == 0
    assert user.num_samples == 0

    project = db.projects.get(project.id)
    db.refresh(project)
    assert project is not None
    assert len(project.samples) == 0

    seq_request = db.seq_requests.get(seq_request.id)
    db.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == 0
    assert seq_request.num_libraries == 0


def test_files(db: DBHandler):
    seq_request = create_seq_request(db, create_user(db))
    NUM_FILES = len(db.media_files.find(limit=None))
    file = create_file(db, seq_request=seq_request)
    assert len(db.media_files.find(limit=None)) == NUM_FILES + 1
    create_file(db, seq_request=seq_request)
    create_file(db, seq_request=seq_request)
    assert len(db.media_files.find(limit=None)) == NUM_FILES + 3
    db.media_files.delete(file.id)
    assert len(db.media_files.find(limit=None)) == NUM_FILES + 2
    db.seq_requests.delete(seq_request.id)
    assert len(db.media_files.find(limit=None)) == NUM_FILES


def test_delete_media_file_unlinks_ba_report(db: DBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)
    library = create_library(db, user, seq_request)
    sample = create_sample(db, user, create_project(db, user))
    pool = create_pool(db, user, seq_request)
    file = create_file(db, seq_request=seq_request)

    library.ba_report_id = file.id
    sample.ba_report_id = file.id
    pool.ba_report_id = file.id
    db.libraries.update(library)
    db.samples.update(sample)
    db.pools.update(pool)
    db.flush()

    db.media_files.delete(file.id)

    library = db.libraries.get(library.id)
    sample = db.samples.get(sample.id)
    pool = db.pools.get(pool.id)
    assert library is not None
    assert sample is not None
    assert pool is not None
    assert library.ba_report_id is None
    assert sample.ba_report_id is None
    assert pool.ba_report_id is None
    assert db.media_files.get(file.id) is None


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

    db.seq_requests.update(req_2)
    db.projects.update(p2)
    db.flush()

    assert len(db.seq_requests.find(user_id=user_1.id, limit=None)[0]) == 2
    assert len(db.seq_requests.find(user_id=user_2.id, limit=None)[0]) == 1
    assert len(db.projects.find(user_id=user_1.id, limit=None)[0]) == 2
    assert len(db.projects.find(user_id=user_2.id, limit=None)[0]) == 1
