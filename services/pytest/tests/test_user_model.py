from opengsync_db import SyncDBHandler, queries as Q
from opengsync_db.categories import UserRole

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library, create_pool,
)


def test_create_user(db: SyncDBHandler):
    old_users = db.session.get_all(Q.user.select(), limit=None)
    new_user = db.session.save(Q.user.create(
        email="new@user.com",
        hashed_password="password",
        first_name="test",
        last_name="user",
        role=UserRole.ADMIN,
    ), flush=True)
    assert new_user.email == "new@user.com"
    assert new_user.first_name == "test"
    assert new_user.last_name == "user"
    assert new_user.role == UserRole.ADMIN
    assert new_user.password == "password"
    
    users = db.session.get_all(Q.user.select(), limit=None)
    assert len(users) == len(old_users) + 1 == db.session.count(Q.user.select())


def test_update_user(db: SyncDBHandler):
    user = db.session.save(Q.user.create(email="user", hashed_password="password", first_name="test", last_name="user", role=UserRole.ADMIN))
    assert user.email == "user"
    assert user.first_name == "test"
    assert user.last_name == "user"
    assert user.role == UserRole.ADMIN
    assert user.password == "password"

    user.role = UserRole.CLIENT
    user.email = "new_email@email.com"
    user.password = "updated_password"
    db.session.save(user)

    assert user.email == "new_email@email.com"
    assert user.role == UserRole.CLIENT
    assert user.password == "updated_password"


def test_delete_user(db: SyncDBHandler):
    old_users = db.session.get_all(Q.user.select(), limit=None)
    user = db.session.save(Q.user.create(email="user", hashed_password="password", first_name="test", last_name="user", role=UserRole.ADMIN))
    users = db.session.get_all(Q.user.select(), limit=None)
    assert len(old_users) + 1 == len(users)
    db.session.delete(user)
    db.session.commit()
    users = db.session.get_all(Q.user.select(), limit=None)
    assert len(old_users) == len(users) == db.session.count(Q.user.select())


def test_user_links(db: SyncDBHandler):
    user = create_user(db)
    project = create_project(db, user)
    user = db.session.first(Q.user.select(id=user.id))
    assert user is not None

    assert len(user.projects) == 1
    assert user.projects[0].id == project.id
    assert user.num_projects == 1

    sample = create_sample(db, user, project)
    user = db.session.first(Q.user.select(id=user.id))
    project = db.session.first(Q.project.select(id=project.id))
    assert user is not None
    assert project is not None

    assert len(user.samples) == 1
    assert user.samples[0].id == sample.id
    assert user.num_samples == 1
    assert len(project.samples) == 1
    assert project.samples[0].id == sample.id

    seq_request = create_seq_request(db, user)
    
    user = db.session.first(Q.user.select(id=user.id))
    assert user is not None

    assert len(user.requests) == 1
    assert user.requests[0].id == seq_request.id
    assert user.num_seq_requests == 1

    library = create_library(db, user, seq_request)
    user = db.session.first(Q.user.select(id=user.id))
    seq_request = db.session.first(Q.seq_request.select(id=seq_request.id))
    assert user is not None
    assert seq_request is not None

    assert len(user.libraries) == 1
    assert user.libraries[0].id == library.id
    assert len(seq_request.libraries) == 1
    assert seq_request.libraries[0].id == library.id
    assert seq_request.num_libraries == 1

    db.actions.link_sample_library(sample.id, library.id)

    sample = db.session.first(Q.sample.select(id=sample.id))
    library = db.session.first(Q.library.select(id=library.id))
    assert sample is not None
    assert library is not None

    assert sample.num_libraries == 1
    assert len(sample.library_links) == 1
    assert sample.library_links[0].library_id == library.id
    assert library.num_samples == 1
    assert len(library.sample_links) == 1
    assert library.sample_links[0].sample_id == sample.id

    pool = create_pool(db, user, seq_request)

    user = db.session.first(Q.user.select(id=user.id))
    assert user is not None
    assert len(user.pools) == 1

    seq_request = db.session.first(Q.seq_request.select(id=seq_request.id))
    assert seq_request is not None
    assert len(seq_request.pools) == 1
    assert seq_request.pools[0].id == pool.id

    library.pool_id = pool.id
    db.session.save(library, flush=True)

    db.session.refresh(library)
    db.session.refresh(pool)
    db.session.refresh(seq_request)

    assert pool.num_libraries == 1
    assert len(pool.libraries) == 1
    assert pool.id == library.pool_id
    assert len(seq_request.pools) == 1
    assert seq_request.pools[0].id == pool.id

    db.session.delete(library, flush=True)
    libraries = db.session.get_all(Q.library.select(), limit=None)
    assert len(libraries) == 0 == db.session.count(Q.library.select())
    samples = db.session.get_all(Q.sample.select(), limit=None)
    assert len(samples) == 0 == db.session.count(Q.sample.select())

    db.session.delete(pool)
    pools = db.session.get_all(Q.pool.select(), limit=None)
    assert len(pools) == 0 == db.session.count(Q.pool.select())

    db.session.refresh(seq_request)
    assert seq_request is not None
    assert seq_request.num_libraries == 0
    assert len(seq_request.libraries) == 0
    
    db.session.refresh(project)
    assert project is not None
    assert project.num_samples == 0
    assert len(project.samples) == 0
    
    db.session.refresh(user)
    assert user is not None
    assert user.num_seq_requests == 1
    assert len(user.requests) == 1
    assert user.num_projects == 1
    assert len(user.projects) == 1
    assert user.num_samples == 0
    assert len(user.samples) == 0
    assert len(user.pools) == 0

    db.session.delete(seq_request)
    seq_requests = db.session.get_all(Q.seq_request.select(), limit=None)
    assert len(seq_requests) == 0 == db.session.count(Q.seq_request.select())

    db.session.refresh(user)
    assert user is not None
    assert user.num_seq_requests == 0
    assert len(user.requests) == 0
