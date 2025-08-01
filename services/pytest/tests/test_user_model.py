from opengsync_db import DBHandler
from opengsync_db.categories import UserRole

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library, create_pool,
)


def test_create_user(db: DBHandler):
    old_users, _ = db.get_users(limit=None)
    new_user = db.create_user(
        email="new@user.com",
        hashed_password="password",
        first_name="test",
        last_name="user",
        role=UserRole.ADMIN,
    )
    assert new_user.email == "new@user.com"
    assert new_user.first_name == "test"
    assert new_user.last_name == "user"
    assert new_user.role == UserRole.ADMIN
    assert new_user.password == "password"
    
    users, _ = db.get_users(limit=None)
    assert len(users) == len(old_users) + 1


def test_update_user(db: DBHandler):
    user = db.create_user(email="user", hashed_password="password", first_name="test", last_name="user", role=UserRole.ADMIN)
    assert user.email == "user"
    assert user.first_name == "test"
    assert user.last_name == "user"
    assert user.role == UserRole.ADMIN
    assert user.password == "password"

    user.role_id = UserRole.CLIENT.id
    user.email = "new_email@email.com"
    user.password = "updated_password"
    user = db.update_user(user)

    assert user.email == "new_email@email.com"
    assert user.role == UserRole.CLIENT
    assert user.password == "updated_password"


def test_delete_user(db: DBHandler):
    old_users, _ = db.get_users(limit=None)
    user = db.create_user(email="user", hashed_password="password", first_name="test", last_name="user", role=UserRole.ADMIN)
    users, _ = db.get_users(limit=None)
    assert len(old_users) + 1 == len(users)
    db.delete_user(user.id)
    db.commit()
    users, _ = db.get_users(limit=None)
    assert len(old_users) == len(users)


def test_user_links(db: DBHandler):
    user = create_user(db)
    project = create_project(db, user)
    user = db.get_user(user.id)
    assert user is not None

    assert len(user.projects) == 1
    assert user.projects[0].id == project.id
    assert user.num_projects == 1

    sample = create_sample(db, user, project)
    user = db.get_user(user.id)
    project = db.get_project(project.id)
    assert user is not None
    assert project is not None

    assert len(user.samples) == 1
    assert user.samples[0].id == sample.id
    assert user.num_samples == 1
    assert len(project.samples) == 1
    assert project.samples[0].id == sample.id

    seq_request = create_seq_request(db, user)
    
    user = db.get_user(user.id)
    assert user is not None

    assert len(user.requests) == 1
    assert user.requests[0].id == seq_request.id
    assert user.num_seq_requests == 1

    library = create_library(db, user, seq_request)
    user = db.get_user(user.id)
    seq_request = db.get_seq_request(seq_request.id)
    assert user is not None
    assert seq_request is not None

    assert len(user.libraries) == 1
    assert user.libraries[0].id == library.id
    assert len(seq_request.libraries) == 1
    assert seq_request.libraries[0].id == library.id
    assert seq_request.num_libraries == 1

    db.link_sample_library(sample.id, library.id)

    sample = db.get_sample(sample.id)
    library = db.get_library(library.id)
    assert sample is not None
    assert library is not None

    assert sample.num_libraries == 1
    assert len(sample.library_links) == 1
    assert sample.library_links[0].library_id == library.id
    assert library.num_samples == 1
    assert len(library.sample_links) == 1
    assert library.sample_links[0].sample_id == sample.id

    pool = create_pool(db, user, seq_request)

    user = db.get_user(user.id)
    assert user is not None
    assert len(user.pools) == 1

    seq_request = db.get_seq_request(seq_request.id)
    assert seq_request is not None
    assert len(seq_request.pools) == 1
    assert seq_request.pools[0].id == pool.id

    db.add_library_to_pool(library.id, pool.id)

    library = db.get_library(library.id)
    pool = db.get_pool(pool.id)
    db.refresh(pool)
    seq_request = db.get_seq_request(seq_request.id)
    assert library is not None
    assert pool is not None
    assert seq_request is not None

    assert pool.num_libraries == 1
    assert len(pool.libraries) == 1
    assert pool.id == library.pool_id
    assert len(seq_request.pools) == 1
    assert seq_request.pools[0].id == pool.id

    db.delete_library(library.id)
    libraries, _ = db.get_libraries(limit=None)
    assert len(libraries) == 0
    samples, _ = db.get_samples(limit=None)
    assert len(samples) == 0

    db.delete_pool(pool.id)
    pools, _ = db.get_pools(limit=None)
    assert len(pools) == 0

    seq_request = db.get_seq_request(seq_request.id)
    db.refresh(seq_request)
    assert seq_request is not None
    assert seq_request.num_libraries == 0
    assert len(seq_request.libraries) == 0
    
    project = db.get_project(project.id)
    db.refresh(project)
    assert project is not None
    assert project.num_samples == 0
    assert len(project.samples) == 0
    
    user = db.get_user(user.id)
    db.refresh(user)
    assert user is not None
    assert user.num_seq_requests == 1
    assert len(user.requests) == 1
    assert user.num_projects == 1
    assert len(user.projects) == 1
    assert user.num_samples == 0
    assert len(user.samples) == 0
    assert len(user.pools) == 0

    db.delete_seq_request(seq_request.id)
    seq_requests, _ = db.get_seq_requests(limit=None)
    assert len(seq_requests) == 0

    user = db.get_user(user.id)
    db.refresh(user)
    assert user is not None
    assert user.num_seq_requests == 0
    assert len(user.requests) == 0
