import pytest

from limbless import models
from limbless.core import exceptions, DBHandler

@pytest.fixture(scope="function", autouse=True)
def db_handler():
    return DBHandler(":memory:")

def test_link_project_user(db_handler):
    project = db_handler.create_project(
        name="project",
        description="description",
    )
    assert len(db_handler.get_project_users(project.id)) == 0

    user = db_handler.create_user(
        email="user",
        password="1234",
        role=1
    )
    assert len(db_handler.get_user_projects(user.id)) == 0

    project_user_link = db_handler.link_project_user(
        project.id, user.id, role=models.ProjectRole.OWNER
    )
    assert project_user_link is not None
    assert project_user_link.project_id == project.id
    assert project_user_link.user_id == user.id
    assert project_user_link.role == models.ProjectRole.OWNER
    
    project_users = db_handler.get_project_users(project.id)
    assert len(project_users) == 1
    assert project_users[0] == user

    user_projects = db_handler.get_user_projects(user.id)
    assert len(user_projects) == 1
    assert user_projects[0] == project

    # Try non existent project
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.link_project_user(
            -1, user.id, role=models.ProjectRole.OWNER
        )

    # Try non existent user
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.link_project_user(
            project.id, -1, role=models.ProjectRole.OWNER
        )

    # Try duplicate link
    with pytest.raises(exceptions.LinkAlreadyExists):
        db_handler.link_project_user(
            project.id, user.id, role=models.ProjectRole.OWNER
        )

    # Try invalid role
    with pytest.raises(exceptions.InvalidRole):
        db_handler.link_project_user(
            project.id, user.id, role=-1
        )

def test_unlink_project_user(db_handler):
    project = db_handler.create_project(
        name="project",
        description="description",
    )

    user = db_handler.create_user(
        email="user",
        password="1234",
        role=1
    )

    project_user_link = db_handler.link_project_user(
        project.id, user.id, role=models.ProjectRole.OWNER
    )
    assert project_user_link is not None

    db_handler.unlink_project_user(project.id, user.id)
    assert len(db_handler.get_project_users(project.id)) == 0
    assert len(db_handler.get_user_projects(user.id)) == 0

    # Try non existent link
    with pytest.raises(exceptions.LinkDoesNotExist):
        db_handler.unlink_project_user(project.id, user.id)

    # Try non existent project
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.unlink_project_user(-1, user.id)

    # Try non existent user
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.unlink_project_user(project.id, -1)