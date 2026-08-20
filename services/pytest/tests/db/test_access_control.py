"""DB-level AccessLevel matrices for Q.*.permissions.

These pin the SQL rules. HTTP enforcement lives in tests/server/test_access.py.
"""
from opengsync_db import SyncSession, queries as Q, categories as C

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_pool, create_group,
)


def _level(session: SyncSession, statement) -> C.AccessLevel:
    return session.get_access_level(statement)


def _affiliate(session: SyncSession, user, group, type: C.AffiliationType):
    session.save(Q.affiliation.create(user=user, group=group, type=type), flush=True)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

def test_project_draft_owner_write_stranger_none(session: SyncSession):
    owner = create_user(session)
    stranger = create_user(session)
    project = create_project(session, owner)

    assert _level(session, Q.project.permissions(project.id, owner.id)) == C.AccessLevel.WRITE
    assert _level(session, Q.project.permissions(project.id, stranger.id)) == C.AccessLevel.NONE


def test_project_processing_owner_read_stranger_none(session: SyncSession):
    owner = create_user(session)
    stranger = create_user(session)
    project = create_project(session, owner)
    project.status = C.ProjectStatus.PROCESSING
    session.save(project, flush=True)

    assert _level(session, Q.project.permissions(project.id, owner.id)) == C.AccessLevel.READ
    assert _level(session, Q.project.permissions(project.id, stranger.id)) == C.AccessLevel.NONE


def test_project_draft_group_member_write(session: SyncSession):
    owner = create_user(session)
    member = create_user(session)
    group = create_group(session)
    _affiliate(session, member, group, C.AffiliationType.MEMBER)
    project = session.save(Q.project.create(
        title="grouped", description="d", owner_id=owner.id, group_id=group.id,
    ), flush=True)

    assert _level(session, Q.project.permissions(project.id, member.id)) == C.AccessLevel.WRITE


def test_project_processing_group_member_read(session: SyncSession):
    owner = create_user(session)
    member = create_user(session)
    group = create_group(session)
    _affiliate(session, member, group, C.AffiliationType.MEMBER)
    project = session.save(Q.project.create(
        title="grouped", description="d", owner_id=owner.id, group_id=group.id,
    ), flush=True)
    project.status = C.ProjectStatus.PROCESSING
    session.save(project, flush=True)

    assert _level(session, Q.project.permissions(project.id, member.id)) == C.AccessLevel.READ
    assert _level(session, Q.project.permissions(project.id, owner.id)) == C.AccessLevel.READ


def test_project_draft_assignee_has_none(session: SyncSession):
    owner = create_user(session)
    assignee = create_user(session)
    project = create_project(session, owner)
    project.assignees.append(assignee)
    session.save(project, flush=True)

    assert _level(session, Q.project.permissions(project.id, assignee.id)) == C.AccessLevel.NONE


def test_project_insider_and_admin(session: SyncSession):
    owner = create_user(session)
    insider = session.save(Q.user.create(
        email="tech@example.com", hashed_password="x", first_name="T", last_name="I",
        role=C.UserRole.TECHNICIAN,
    ), flush=True)
    admin = session.save(Q.user.create(
        email="adm@example.com", hashed_password="x", first_name="A", last_name="D",
        role=C.UserRole.ADMIN,
    ), flush=True)
    project = create_project(session, owner)

    assert _level(session, Q.project.permissions(project.id, insider.id)) == C.AccessLevel.INSIDER
    assert _level(session, Q.project.permissions(project.id, admin.id)) == C.AccessLevel.ADMIN


# ---------------------------------------------------------------------------
# Seq request
# ---------------------------------------------------------------------------

def test_seq_request_draft_requestor_write_stranger_none(session: SyncSession):
    requestor = create_user(session)
    stranger = create_user(session)
    seq_request = create_seq_request(session, requestor)

    assert _level(session, Q.seq_request.permissions(seq_request.id, requestor.id)) == C.AccessLevel.WRITE
    assert _level(session, Q.seq_request.permissions(seq_request.id, stranger.id)) == C.AccessLevel.NONE


def test_seq_request_submitted_stranger_still_none(session: SyncSession):
    requestor = create_user(session)
    stranger = create_user(session)
    seq_request = create_seq_request(session, requestor)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.save(seq_request, flush=True)

    assert _level(session, Q.seq_request.permissions(seq_request.id, requestor.id)) == C.AccessLevel.READ
    assert _level(session, Q.seq_request.permissions(seq_request.id, stranger.id)) == C.AccessLevel.NONE


def test_seq_request_assignee_has_none(session: SyncSession):
    requestor = create_user(session)
    assignee = create_user(session)
    seq_request = create_seq_request(session, requestor)
    seq_request.assignees.append(assignee)
    session.save(seq_request, flush=True)

    assert _level(session, Q.seq_request.permissions(seq_request.id, assignee.id)) == C.AccessLevel.NONE


def test_seq_request_group_member_write(session: SyncSession):
    requestor = create_user(session)
    member = create_user(session)
    group = create_group(session)
    _affiliate(session, member, group, C.AffiliationType.MEMBER)
    seq_request = create_seq_request(session, requestor)
    seq_request.group = group
    session.save(seq_request, flush=True)

    assert _level(session, Q.seq_request.permissions(seq_request.id, member.id)) == C.AccessLevel.WRITE


def test_seq_request_submitted_group_member_read(session: SyncSession):
    requestor = create_user(session)
    member = create_user(session)
    group = create_group(session)
    _affiliate(session, member, group, C.AffiliationType.MEMBER)
    seq_request = create_seq_request(session, requestor)
    seq_request.group = group
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.save(seq_request, flush=True)

    assert _level(session, Q.seq_request.permissions(seq_request.id, member.id)) == C.AccessLevel.READ
    assert _level(session, Q.seq_request.permissions(seq_request.id, requestor.id)) == C.AccessLevel.READ


# ---------------------------------------------------------------------------
# Sample — inherit from project
# ---------------------------------------------------------------------------

def test_sample_follows_draft_project_owner_write_stranger_none(session: SyncSession):
    owner = create_user(session)
    stranger = create_user(session)
    project = create_project(session, owner)
    sample = create_sample(session, owner, project)

    assert _level(session, Q.sample.permissions(sample.id, owner.id)) == C.AccessLevel.WRITE
    assert _level(session, Q.sample.permissions(sample.id, stranger.id)) == C.AccessLevel.NONE


def test_sample_follows_processing_project_owner_read(session: SyncSession):
    owner = create_user(session)
    project = create_project(session, owner)
    sample = create_sample(session, owner, project)
    project.status = C.ProjectStatus.PROCESSING
    session.save(project, flush=True)

    assert _level(session, Q.sample.permissions(sample.id, owner.id)) == C.AccessLevel.READ


def test_sample_follows_draft_project_group_member_write(session: SyncSession):
    owner = create_user(session)
    member = create_user(session)
    group = create_group(session)
    _affiliate(session, member, group, C.AffiliationType.MEMBER)
    project = session.save(Q.project.create(
        title="grouped", description="d", owner_id=owner.id, group_id=group.id,
    ), flush=True)
    sample = create_sample(session, owner, project)

    assert _level(session, Q.sample.permissions(sample.id, member.id)) == C.AccessLevel.WRITE


def test_sample_follows_processing_project_group_member_read(session: SyncSession):
    owner = create_user(session)
    member = create_user(session)
    group = create_group(session)
    _affiliate(session, member, group, C.AffiliationType.MEMBER)
    project = session.save(Q.project.create(
        title="grouped", description="d", owner_id=owner.id, group_id=group.id,
    ), flush=True)
    sample = create_sample(session, owner, project)
    project.status = C.ProjectStatus.PROCESSING
    session.save(project, flush=True)

    assert _level(session, Q.sample.permissions(sample.id, member.id)) == C.AccessLevel.READ
    assert _level(session, Q.sample.permissions(sample.id, owner.id)) == C.AccessLevel.READ


# ---------------------------------------------------------------------------
# Library — inherit from seq request (library.owner_id is ignored)
# ---------------------------------------------------------------------------

def test_library_follows_draft_seq_request(session: SyncSession):
    owner = create_user(session)
    other = create_user(session)
    seq_request = create_seq_request(session, owner)
    library = create_library(session, other, seq_request)

    assert _level(session, Q.library.permissions(library.id, owner.id)) == C.AccessLevel.WRITE
    assert _level(session, Q.library.permissions(library.id, other.id)) == C.AccessLevel.NONE


def test_library_follows_submitted_seq_request_read(session: SyncSession):
    owner = create_user(session)
    seq_request = create_seq_request(session, owner)
    library = create_library(session, owner, seq_request)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.save(seq_request, flush=True)

    assert _level(session, Q.library.permissions(library.id, owner.id)) == C.AccessLevel.READ


def test_library_follows_draft_seq_request_group_member_write(session: SyncSession):
    requestor = create_user(session)
    member = create_user(session)
    group = create_group(session)
    _affiliate(session, member, group, C.AffiliationType.MEMBER)
    seq_request = create_seq_request(session, requestor)
    seq_request.group = group
    session.save(seq_request, flush=True)
    library = create_library(session, requestor, seq_request)

    assert _level(session, Q.library.permissions(library.id, member.id)) == C.AccessLevel.WRITE


def test_library_follows_submitted_seq_request_group_member_read(session: SyncSession):
    requestor = create_user(session)
    member = create_user(session)
    group = create_group(session)
    _affiliate(session, member, group, C.AffiliationType.MEMBER)
    seq_request = create_seq_request(session, requestor)
    seq_request.group = group
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.save(seq_request, flush=True)
    library = create_library(session, requestor, seq_request)

    assert _level(session, Q.library.permissions(library.id, member.id)) == C.AccessLevel.READ
    assert _level(session, Q.library.permissions(library.id, requestor.id)) == C.AccessLevel.READ


def test_pool_follows_seq_request(session: SyncSession):
    owner = create_user(session)
    other = create_user(session)
    seq_request = create_seq_request(session, owner)
    pool = create_pool(session, other, seq_request)

    assert _level(session, Q.pool.permissions(pool.id, owner.id)) == C.AccessLevel.WRITE
    assert _level(session, Q.pool.permissions(pool.id, other.id)) == C.AccessLevel.NONE


def test_pool_without_seq_request_is_none_for_client(session: SyncSession):
    owner = create_user(session)
    pool = session.save(Q.pool.create(
        name="orphan",
        owner_id=owner.id,
        contact_name="n",
        contact_email="n@e.com",
        pool_type=C.PoolType.EXTERNAL,
        clone_number=0,
        seq_request_id=None,
    ), flush=True)

    assert _level(session, Q.pool.permissions(pool.id, owner.id)) == C.AccessLevel.NONE


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

def test_group_member_read_manager_write_outsider_none(session: SyncSession):
    member = create_user(session)
    manager = create_user(session)
    outsider = create_user(session)
    group = create_group(session)
    _affiliate(session, member, group, C.AffiliationType.MEMBER)
    _affiliate(session, manager, group, C.AffiliationType.MANAGER)

    assert _level(session, Q.group.permissions(group.id, member.id)) == C.AccessLevel.READ
    assert _level(session, Q.group.permissions(group.id, manager.id)) == C.AccessLevel.WRITE
    assert _level(session, Q.group.permissions(group.id, outsider.id)) == C.AccessLevel.NONE


def test_group_owner_write(session: SyncSession):
    owner = create_user(session)
    group = create_group(session)
    _affiliate(session, owner, group, C.AffiliationType.OWNER)

    assert _level(session, Q.group.permissions(group.id, owner.id)) == C.AccessLevel.WRITE


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

def test_user_self_write_other_client_none(session: SyncSession):
    a = create_user(session)
    b = create_user(session)

    assert _level(session, Q.user.permissions(a.id, a.id)) == C.AccessLevel.WRITE
    assert _level(session, Q.user.permissions(b.id, a.id)) == C.AccessLevel.NONE


def test_user_insider_and_admin_viewing_other(session: SyncSession):
    client = create_user(session)
    insider = session.save(Q.user.create(
        email="tech2@example.com", hashed_password="x", first_name="T", last_name="I",
        role=C.UserRole.TECHNICIAN,
    ), flush=True)
    admin = session.save(Q.user.create(
        email="adm2@example.com", hashed_password="x", first_name="A", last_name="D",
        role=C.UserRole.ADMIN,
    ), flush=True)

    assert _level(session, Q.user.permissions(client.id, insider.id)) == C.AccessLevel.INSIDER
    assert _level(session, Q.user.permissions(client.id, admin.id)) == C.AccessLevel.ADMIN
