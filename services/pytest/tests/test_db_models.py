from opengsync_db import SyncDBHandler, queries as Q, categories as C

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_file, create_group
)  # noqa


def test_mux_links(db: SyncDBHandler):
    user = create_user(db)
    project = create_project(db, user)
    seq_request = create_seq_request(db, user)
    library = create_library(db, user, seq_request)

    NUM_SAMPLES = 10

    for _ in range(NUM_SAMPLES):
        sample = create_sample(db, user, project)
        db.actions.link_sample_library(
            sample.id, library.id,
            mux=dict(barcode="sequence", pattern="pattern", read="read"),
        )

    db.session.refresh(user)
    assert user is not None
    assert len(user.samples) == NUM_SAMPLES
    assert user.num_samples == NUM_SAMPLES
    assert len(db.session.get_all(Q.seq_request.select(), limit=None)) == db.session.count(Q.seq_request.select()) == 1
    assert len(db.session.get_all(Q.project.select(), limit=None)) == db.session.count(Q.project.select()) == 1
    db.session.refresh(project)
    assert project is not None
    assert len(project.samples) == NUM_SAMPLES

    db.session.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == 1
    assert seq_request.num_libraries == 1

    db.session.refresh(library)
    assert library is not None
    assert len(library.sample_links) == NUM_SAMPLES
    assert library.num_samples == NUM_SAMPLES

    db.session.delete(library, flush=True)

    db.session.refresh(user)
    assert user is not None
    assert len(user.samples) == 0
    assert user.num_samples == 0

    db.session.refresh(project)
    assert project is not None
    assert len(project.samples) == 0

    db.session.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == 0
    assert seq_request.num_libraries == 0


def test_files(db: SyncDBHandler):
    seq_request = create_seq_request(db, create_user(db))
    NUM_FILES = db.session.count(Q.media_file.select())
    file = create_file(db, seq_request=seq_request)
    assert db.session.count(Q.media_file.select()) == len(db.session.get_all(Q.media_file.select(), limit=None)) == NUM_FILES + 1
    create_file(db, seq_request=seq_request)
    create_file(db, seq_request=seq_request)
    assert db.session.count(Q.media_file.select()) == len(db.session.get_all(Q.media_file.select(), limit=None)) == NUM_FILES + 3
    db.session.delete(file, flush=True)
    assert db.session.count(Q.media_file.select()) == len(db.session.get_all(Q.media_file.select(), limit=None)) == NUM_FILES + 2
    db.session.delete(seq_request, flush=True)
    assert db.session.count(Q.media_file.select()) == NUM_FILES


def test_group_affiliations(db: SyncDBHandler):
    user_1 = create_user(db)
    user_2 = create_user(db)

    group = create_group(db)
    group.user_links.append(Q.affiliation.create(user=user_1, group=group, type=C.AffiliationType.MEMBER))
    db.session.save(group, flush=True)

    _ = create_seq_request(db, user_1)
    req_2 = create_seq_request(db, user_2)

    _ = create_project(db, user_1)
    p2 = create_project(db, user_2)

    req_2.group_id = group.id
    p2.group_id = group.id

    db.session.save(req_2)
    db.session.save(p2)
    db.session.flush()

    assert len(db.session.get_all(Q.seq_request.select(viewer_id=user_1.id), limit=None)) == 2
    assert len(db.session.get_all(Q.seq_request.select(viewer_id=user_2.id), limit=None)) == 1
    assert len(db.session.get_all(Q.project.select(viewer_id=user_1.id), limit=None)) == 2
    assert len(db.session.get_all(Q.project.select(viewer_id=user_2.id), limit=None)) == 1
