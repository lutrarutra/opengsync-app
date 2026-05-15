from opengsync_db import DBHandler

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
)  # noqa


def test_project_merge(db: DBHandler):
    user = create_user(db)
    project_a = create_project(db, user)
    project_b = create_project(db, user)
    seq_request_a = create_seq_request(db, user)
    seq_request_b = create_seq_request(db, user)

    NUM_SAMPLES = 10

    for _ in range(NUM_SAMPLES):
        sample_a = create_sample(db, user, project_a)
        sample_b = create_sample(db, user, project_b)

        library_a = create_library(db, user, seq_request_a)
        library_b = create_library(db, user, seq_request_b)

        db.links.link_sample_library(sample_a.id, library_a.id)
        db.links.link_sample_library(sample_b.id, library_b.id)


    assert len(db.samples.find(limit=None)[0]) == 2 * NUM_SAMPLES
    assert len(db.libraries.find(limit=None)[0]) == 2 * NUM_SAMPLES
    assert len(db.seq_requests.find(limit=None)[0]) == 2
    assert len(db.projects.find(limit=None)[0]) == 2
        
    project_a = db.projects.merge_projects(project_dst=project_a, project_src=project_b)
    db.flush()
    db.refresh(project_a)
    db.refresh(project_b)

    assert len(db.samples.find(limit=None)[0]) == 2 * NUM_SAMPLES
    assert len(db.libraries.find(limit=None)[0]) == 2 * NUM_SAMPLES
    assert len(db.seq_requests.find(limit=None)[0]) == 2
    assert len(db.projects.find(limit=None)[0]) == 2
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


