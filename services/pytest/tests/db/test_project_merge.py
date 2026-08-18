from opengsync_db import SyncSession, actions, queries as Q

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
)  # noqa


def test_project_merge(session: SyncSession):
    user = create_user(session)
    project_a = create_project(session, user)
    project_b = create_project(session, user)
    seq_request_a = create_seq_request(session, user)
    seq_request_b = create_seq_request(session, user)

    NUM_SAMPLES = 10

    for _ in range(NUM_SAMPLES):
        sample_a = create_sample(session, user, project_a)
        sample_b = create_sample(session, user, project_b)

        library_a = create_library(session, user, seq_request_a)
        library_b = create_library(session, user, seq_request_b)

        actions.link_sample_library(session, sample_a.id, library_a.id)
        actions.link_sample_library(session, sample_b.id, library_b.id)


    assert session.count(Q.sample.select()) == 2 * NUM_SAMPLES
    assert session.count(Q.library.select()) == 2 * NUM_SAMPLES
    assert session.count(Q.seq_request.select()) == 2
    assert session.count(Q.project.select()) == 2
        
    project_a = actions.merge_projects(session, project_dst=project_a, project_src=project_b)
    session.flush()
    session.refresh(project_a)
    session.refresh(project_b)

    assert session.count(Q.sample.select()) == 2 * NUM_SAMPLES
    assert session.count(Q.library.select()) == 2 * NUM_SAMPLES
    assert session.count(Q.seq_request.select()) == 2
    assert session.count(Q.project.select()) == 2
    assert len(project_a.samples) == 2 * NUM_SAMPLES
    assert len(project_a.libraries) == 2 * NUM_SAMPLES
    assert len(project_a.seq_requests) == 2
    assert project_a.num_samples == 2 * NUM_SAMPLES
    assert project_a.num_seq_requests == 2
    assert len(project_b.samples) == 0
    assert len(project_b.libraries) == 0
    assert len(project_b.seq_requests) == 0
    assert project_b.num_samples == 0
    assert project_b.num_seq_requests == 0


