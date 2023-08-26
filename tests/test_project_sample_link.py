import pytest

import sqlalchemy

from limbless import models, core
from limbless.core import exceptions, DBHandler

@pytest.fixture(scope="function", autouse=True)
def db_handler():
    return DBHandler(":memory:")

def test_link_project_sample(db_handler):
    project = db_handler.create_project(
        name="project",
        description="description",
    )
    assert len(db_handler.get_project_samples(project.id)) == 0

    sample = db_handler.create_sample(
        name="sample",
        organism="organism",
        index1="index1",
        index2="index2"
    )
    assert len(db_handler.get_sample_projects(sample.id)) == 0

    project_sample_link = db_handler.link_project_sample(project.id, sample.id)
    assert project_sample_link is not None
    assert project_sample_link.project_id == project.id
    assert project_sample_link.sample_id == sample.id
    
    project_samples = db_handler.get_project_samples(project.id)
    assert len(project_samples) == 1
    assert project_samples[0] == sample

    sample_projects = db_handler.get_sample_projects(sample.id)
    assert len(sample_projects) == 1
    assert sample_projects[0] == project

    # Try non existent project
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.link_project_sample(-1, sample.id)

    # Try non existent sample
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.link_project_sample(project.id, -1)

    # # Try duplicate link
    with pytest.raises(exceptions.LinkAlreadyExists):
        db_handler.link_project_sample(project.id, sample.id)

def test_unlink_project_sample(db_handler):
    project = db_handler.create_project(
        name="project",
        description="description",
    )

    sample = db_handler.create_sample(
        name="sample",
        organism="organism",
        index1="index1",
        index2="index2"
    )

    project_sample_link = db_handler.link_project_sample(project.id, sample.id)
    assert project_sample_link is not None

    db_handler.unlink_project_sample(project.id, sample.id)
    assert len(db_handler.get_project_samples(project.id)) == 0
    assert len(db_handler.get_sample_projects(sample.id)) == 0

    # Try non existent link
    with pytest.raises(exceptions.LinkDoesNotExist):
        db_handler.unlink_project_sample(project.id, sample.id)

    # Try non existent project
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.unlink_project_sample(-1, sample.id)

    # Try non existent sample
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.unlink_project_sample(project.id, -1)