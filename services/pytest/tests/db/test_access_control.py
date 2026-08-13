"""DB-level AccessLevel matrices for Q.*.permissions.

These pin the SQL rules. HTTP enforcement lives in tests/server/test_access.py.
"""
from opengsync_db import SyncDBHandler, queries as Q, categories as C

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_pool, create_group,
)


def _level(db: SyncDBHandler, statement) -> C.AccessLevel:
    return db.session.get_access_level(statement)


def _affiliate(db: SyncDBHandler, user, group, type: C.AffiliationType):
    db.session.save(Q.affiliation.create(user=user, group=group, type=type), flush=True)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

def test_project_draft_owner_write_stranger_none(db: SyncDBHandler):
    owner = create_user(db)
    stranger = create_user(db)
    project = create_project(db, owner)

    assert _level(db, Q.project.permissions(project.id, owner.id)) == C.AccessLevel.WRITE
    assert _level(db, Q.project.permissions(project.id, stranger.id)) == C.AccessLevel.NONE


def test_project_processing_is_world_readable(db: SyncDBHandler):
    owner = create_user(db)
    stranger = create_user(db)
    project = create_project(db, owner)
    project.status = C.ProjectStatus.PROCESSING
    db.session.save(project, flush=True)

    assert _level(db, Q.project.permissions(project.id, owner.id)) == C.AccessLevel.READ
    assert _level(db, Q.project.permissions(project.id, stranger.id)) == C.AccessLevel.READ


def test_project_draft_group_member_write(db: SyncDBHandler):
    owner = create_user(db)
    member = create_user(db)
    group = create_group(db)
    _affiliate(db, member, group, C.AffiliationType.MEMBER)
    project = db.session.save(Q.project.create(
        title="grouped", description="d", owner_id=owner.id, group_id=group.id,
    ), flush=True)

    assert _level(db, Q.project.permissions(project.id, member.id)) == C.AccessLevel.WRITE


def test_project_draft_assignee_has_none(db: SyncDBHandler):
    owner = create_user(db)
    assignee = create_user(db)
    project = create_project(db, owner)
    project.assignees.append(assignee)
    db.session.save(project, flush=True)

    assert _level(db, Q.project.permissions(project.id, assignee.id)) == C.AccessLevel.NONE


def test_project_insider_and_admin(db: SyncDBHandler):
    owner = create_user(db)
    insider = db.session.save(Q.user.create(
        email="tech@example.com", hashed_password="x", first_name="T", last_name="I",
        role=C.UserRole.TECHNICIAN,
    ), flush=True)
    admin = db.session.save(Q.user.create(
        email="adm@example.com", hashed_password="x", first_name="A", last_name="D",
        role=C.UserRole.ADMIN,
    ), flush=True)
    project = create_project(db, owner)

    assert _level(db, Q.project.permissions(project.id, insider.id)) == C.AccessLevel.INSIDER
    assert _level(db, Q.project.permissions(project.id, admin.id)) == C.AccessLevel.ADMIN


# ---------------------------------------------------------------------------
# Seq request
# ---------------------------------------------------------------------------

def test_seq_request_draft_requestor_write_stranger_none(db: SyncDBHandler):
    requestor = create_user(db)
    stranger = create_user(db)
    seq_request = create_seq_request(db, requestor)

    assert _level(db, Q.seq_request.permissions(seq_request.id, requestor.id)) == C.AccessLevel.WRITE
    assert _level(db, Q.seq_request.permissions(seq_request.id, stranger.id)) == C.AccessLevel.NONE


def test_seq_request_submitted_stranger_still_none(db: SyncDBHandler):
    requestor = create_user(db)
    stranger = create_user(db)
    seq_request = create_seq_request(db, requestor)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    db.session.save(seq_request, flush=True)

    assert _level(db, Q.seq_request.permissions(seq_request.id, requestor.id)) == C.AccessLevel.READ
    assert _level(db, Q.seq_request.permissions(seq_request.id, stranger.id)) == C.AccessLevel.NONE


def test_seq_request_assignee_has_none(db: SyncDBHandler):
    requestor = create_user(db)
    assignee = create_user(db)
    seq_request = create_seq_request(db, requestor)
    seq_request.assignees.append(assignee)
    db.session.save(seq_request, flush=True)

    assert _level(db, Q.seq_request.permissions(seq_request.id, assignee.id)) == C.AccessLevel.NONE


def test_seq_request_group_member_write(db: SyncDBHandler):
    requestor = create_user(db)
    member = create_user(db)
    group = create_group(db)
    _affiliate(db, member, group, C.AffiliationType.MEMBER)
    seq_request = create_seq_request(db, requestor)
    seq_request.group = group
    db.session.save(seq_request, flush=True)

    assert _level(db, Q.seq_request.permissions(seq_request.id, member.id)) == C.AccessLevel.WRITE


# ---------------------------------------------------------------------------
# Sample / library / pool — follow seq request, not owner_id
# ---------------------------------------------------------------------------

def test_sample_unlinked_is_none_for_client(db: SyncDBHandler):
    owner = create_user(db)
    project = create_project(db, owner)
    sample = create_sample(db, owner, project)

    assert _level(db, Q.sample.permissions(sample.id, owner.id)) == C.AccessLevel.NONE


def test_sample_linked_to_draft_seq_request_write(db: SyncDBHandler):
    owner = create_user(db)
    stranger = create_user(db)
    project = create_project(db, owner)
    seq_request = create_seq_request(db, owner)
    sample = create_sample(db, owner, project)
    library = create_library(db, owner, seq_request)
    db.actions.link_sample_library(sample.id, library.id)

    assert _level(db, Q.sample.permissions(sample.id, owner.id)) == C.AccessLevel.WRITE
    assert _level(db, Q.sample.permissions(sample.id, stranger.id)) == C.AccessLevel.NONE


def test_sample_linked_non_draft_library_is_read(db: SyncDBHandler):
    owner = create_user(db)
    project = create_project(db, owner)
    seq_request = create_seq_request(db, owner)
    sample = create_sample(db, owner, project)
    library = create_library(db, owner, seq_request)
    db.actions.link_sample_library(sample.id, library.id)
    library.status = C.LibraryStatus.SUBMITTED
    db.session.save(library, flush=True)

    assert _level(db, Q.sample.permissions(sample.id, owner.id)) == C.AccessLevel.READ


def test_library_follows_seq_request(db: SyncDBHandler):
    owner = create_user(db)
    other = create_user(db)
    seq_request = create_seq_request(db, owner)
    library = create_library(db, other, seq_request)  # owner_id ignored by SQL

    assert _level(db, Q.library.permissions(library.id, owner.id)) == C.AccessLevel.WRITE
    assert _level(db, Q.library.permissions(library.id, other.id)) == C.AccessLevel.NONE


def test_pool_follows_seq_request(db: SyncDBHandler):
    owner = create_user(db)
    other = create_user(db)
    seq_request = create_seq_request(db, owner)
    pool = create_pool(db, other, seq_request)

    assert _level(db, Q.pool.permissions(pool.id, owner.id)) == C.AccessLevel.WRITE
    assert _level(db, Q.pool.permissions(pool.id, other.id)) == C.AccessLevel.NONE


def test_pool_without_seq_request_is_none_for_client(db: SyncDBHandler):
    owner = create_user(db)
    pool = db.session.save(Q.pool.create(
        name="orphan",
        owner_id=owner.id,
        contact_name="n",
        contact_email="n@e.com",
        pool_type=C.PoolType.EXTERNAL,
        clone_number=0,
        seq_request_id=None,
    ), flush=True)

    assert _level(db, Q.pool.permissions(pool.id, owner.id)) == C.AccessLevel.NONE


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

def test_group_member_read_manager_write_outsider_none(db: SyncDBHandler):
    member = create_user(db)
    manager = create_user(db)
    outsider = create_user(db)
    group = create_group(db)
    _affiliate(db, member, group, C.AffiliationType.MEMBER)
    _affiliate(db, manager, group, C.AffiliationType.MANAGER)

    assert _level(db, Q.group.permissions(group.id, member.id)) == C.AccessLevel.READ
    assert _level(db, Q.group.permissions(group.id, manager.id)) == C.AccessLevel.WRITE
    assert _level(db, Q.group.permissions(group.id, outsider.id)) == C.AccessLevel.NONE


def test_group_owner_write(db: SyncDBHandler):
    owner = create_user(db)
    group = create_group(db)
    _affiliate(db, owner, group, C.AffiliationType.OWNER)

    assert _level(db, Q.group.permissions(group.id, owner.id)) == C.AccessLevel.WRITE


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

def test_user_self_write_other_client_none(db: SyncDBHandler):
    a = create_user(db)
    b = create_user(db)

    assert _level(db, Q.user.permissions(a.id, a.id)) == C.AccessLevel.WRITE
    assert _level(db, Q.user.permissions(b.id, a.id)) == C.AccessLevel.NONE


def test_user_insider_and_admin_viewing_other(db: SyncDBHandler):
    client = create_user(db)
    insider = db.session.save(Q.user.create(
        email="tech2@example.com", hashed_password="x", first_name="T", last_name="I",
        role=C.UserRole.TECHNICIAN,
    ), flush=True)
    admin = db.session.save(Q.user.create(
        email="adm2@example.com", hashed_password="x", first_name="A", last_name="D",
        role=C.UserRole.ADMIN,
    ), flush=True)

    assert _level(db, Q.user.permissions(client.id, insider.id)) == C.AccessLevel.INSIDER
    assert _level(db, Q.user.permissions(client.id, admin.id)) == C.AccessLevel.ADMIN
