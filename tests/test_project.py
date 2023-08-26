import pytest

from limbless import models
from limbless.core import exceptions, DBHandler

@pytest.fixture(scope="function", autouse=True)
def db_handler():
    return DBHandler(":memory:")

def test_create_project(db_handler):
    project = db_handler.create_project(
        name="project",
        description="description",
    )
    assert project.id is not None
    assert project.name == "project"
    assert project.description == "description"

    projects = db_handler.get_projects()
    assert len(projects) == 1
    assert projects[0] == project

def test_get_project(db_handler):
    project = db_handler.create_project(
        name="project",
        description="description",
    )
    q_project = db_handler.get_project(project.id)
    assert q_project == project
    assert db_handler.get_project(-1) is None

def test_update_project(db_handler):
    project = db_handler.create_project(
        name="project",
        description="description",
    )
    project.name = "project2"
    project.description = "description2"
    db_handler.update_project(project.id, name="project2", description="description2")
    assert project.name == "project2"
    assert project.description == "description2"

    # Non existent project_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.update_project(-1, name="project2", description="description2")

def test_delete_project(db_handler):
    project = db_handler.create_project(
        name="project",
        description="description",
    )
    db_handler.delete_project(project.id)
    assert db_handler.get_project(project.id) is None

    # Non existent project_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.delete_project(-1)

def test_duplicate_project(db_handler):
    with pytest.raises(exceptions.NotUniqueValue):
        db_handler.create_project(
            name="project",
            description="description",
        )
        db_handler.create_project(
            name="project",
            description="description",
        )