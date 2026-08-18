from opengsync_db import SyncSession, actions, queries as Q, categories as C

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_file, create_group
)  # noqa


def test_mux_links(session: SyncSession):
    user = create_user(session)
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)

    NUM_SAMPLES = 10

    for _ in range(NUM_SAMPLES):
        sample = create_sample(session, user, project)
        actions.link_sample_library(
            session, sample.id, library.id,
            mux=dict(barcode="sequence", pattern="pattern", read="read"),
        )

    session.refresh(user)
    assert user is not None
    assert len(user.samples) == NUM_SAMPLES
    assert user.num_samples == NUM_SAMPLES
    assert len(session.get_all(Q.seq_request.select(), limit=None)) == session.count(Q.seq_request.select()) == 1
    assert len(session.get_all(Q.project.select(), limit=None)) == session.count(Q.project.select()) == 1
    session.refresh(project)
    assert project is not None
    assert len(project.samples) == NUM_SAMPLES

    session.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == 1
    assert seq_request.num_libraries == 1

    session.refresh(library)
    assert library is not None
    assert len(library.sample_links) == NUM_SAMPLES
    assert library.num_samples == NUM_SAMPLES

    session.delete(library, flush=True)

    session.refresh(user)
    assert user is not None
    assert len(user.samples) == 0
    assert user.num_samples == 0

    session.refresh(project)
    assert project is not None
    assert len(project.samples) == 0

    session.refresh(seq_request)
    assert seq_request is not None
    assert len(seq_request.libraries) == 0
    assert seq_request.num_libraries == 0


def test_files(session: SyncSession):
    seq_request = create_seq_request(session, create_user(session))
    NUM_FILES = session.count(Q.media_file.select())
    file = create_file(session, seq_request=seq_request)
    assert session.count(Q.media_file.select()) == len(session.get_all(Q.media_file.select(), limit=None)) == NUM_FILES + 1
    create_file(session, seq_request=seq_request)
    create_file(session, seq_request=seq_request)
    assert session.count(Q.media_file.select()) == len(session.get_all(Q.media_file.select(), limit=None)) == NUM_FILES + 3
    session.delete(file, flush=True)
    assert session.count(Q.media_file.select()) == len(session.get_all(Q.media_file.select(), limit=None)) == NUM_FILES + 2
    session.delete(seq_request, flush=True)
    assert session.count(Q.media_file.select()) == NUM_FILES


def test_group_affiliations(session: SyncSession):
    user_1 = create_user(session)
    user_2 = create_user(session)

    group = create_group(session)
    group.user_links.append(Q.affiliation.create(user=user_1, group=group, type=C.AffiliationType.MEMBER))
    session.save(group, flush=True)

    _ = create_seq_request(session, user_1)
    req_2 = create_seq_request(session, user_2)

    _ = create_project(session, user_1)
    p2 = create_project(session, user_2)

    req_2.group_id = group.id
    p2.group_id = group.id

    session.save(req_2)
    session.save(p2)
    session.flush()

    assert len(session.get_all(Q.seq_request.select(viewer_id=user_1.id), limit=None)) == 2
    assert len(session.get_all(Q.seq_request.select(viewer_id=user_2.id), limit=None)) == 1
    assert len(session.get_all(Q.project.select(viewer_id=user_1.id), limit=None)) == 2
    assert len(session.get_all(Q.project.select(viewer_id=user_2.id), limit=None)) == 1
