"""actions.merge_users: move everything referencing a source user to a destination user, then delete the source.

- every foreign key to ``lims_user`` is re-pointed (a guard test fails when a new one is added
  without being handled);
- assignee links and group affiliations are deduplicated; in a shared group the stronger affiliation wins;
- the destination keeps its email and password, gets the more privileged role and the later last login;
- passkeys move when the destination has no WebAuthn handle yet, otherwise they are deleted;
- rejected before any change: same user twice, both users owning a project with the same title.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from opengsync_db import SyncSession, actions, models, queries as Q
from opengsync_db.categories import (
    AffiliationType, ChecklistType, EventType, ExperimentWorkFlow, MediaFileType, OperationKind, UserRole,
)

from .create_units import (
    create_experiment, create_group, create_lab_prep, create_library, create_plate, create_pool,
    create_pool_design, create_project, create_sample, create_seq_request, create_todo_comment, create_user,
)

LINK_TABLES = {
    ("project_assignee_link", "user_id"),
    ("seq_request_assignee_link", "user_id"),
    ("user_affiliation", "user_id"),
    ("user_passkey", "user_id"),
}


def _column_key(column) -> tuple[str, str]:
    table_column = column.property.columns[0]
    return table_column.table.name, table_column.name


def _references(session: SyncSession, user: models.User) -> None:
    """Creates one row of every kind that references ``user``."""
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    create_sample(session, user, project)
    create_library(session, user, seq_request)
    pool = create_pool(session, user, seq_request)
    create_plate(session, user)
    create_lab_prep(session, user)
    create_experiment(session, user, ExperimentWorkFlow.NOVASEQ_6K_SP_STD)
    create_todo_comment(session, user, pool_design_id=create_pool_design(session).id)
    session.add_all([
        models.PoolDilution(identifier="A", pool_id=pool.id, operator_id=user.id, qubit_concentration=1.0),
        Q.media_file.create(name="file", type=MediaFileType.CUSTOM, uploader_id=user.id, extension="pdf", size_bytes=1),
        Q.comment.create(text="comment", author=user, seq_request_id=seq_request.id),
        Q.event.create(title="event", timestamp_utc=datetime.now(timezone.utc), type=EventType.CUSTOM, user_id=user.id),
        Q.api_token.create(owner=user, time_valid_min=60),
        Q.share_token.create(owner=user, time_valid_min=60, paths=[]),
        models.OperationRun(operation="test.op", kind=OperationKind.ACTION, actor_id=user.id),
        models.ChecklistLog(
            checklist_type=ChecklistType.SEQ_REQUEST_REVIEW, step="step", checked=True,
            actor_id=user.id, seq_request_id=seq_request.id,
        ),
        models.links.ProjectAssigneeLink(project_id=project.id, user_id=user.id),
        models.links.SeqRequestAssigneeLink(seq_request_id=seq_request.id, user_id=user.id),
        Q.affiliation.create(user=user, group=create_group(session), type=AffiliationType.MEMBER),
    ])
    session.flush()


def _ids_referencing(session: SyncSession, column, user_id: int) -> set:
    model = column.class_
    pk = sa.inspect(model).primary_key
    return set(tuple(row) for row in session.execute(sa.select(*pk).where(column == user_id)).all())


def _passkey(session: SyncSession, user: models.User) -> models.UserPasskey:
    return session.save(Q.passkey.create(
        user=user, credential_id=os.urandom(16), public_key=b"key", sign_count=0, name="key",
    ), flush=True)


def _merge(session: SyncSession, dst: models.User, src: models.User) -> models.User:
    user = actions.merge_users(session, user_dst=dst, user_src=src)
    session.expire_all()
    return user


@pytest.fixture
def users(session: SyncSession) -> tuple[models.User, models.User]:
    return create_user(session), create_user(session)


def test_every_user_foreign_key_is_handled():
    referencing = {
        (table.name, fk.parent.name)
        for table in models.User.metadata.tables.values()
        for fk in table.foreign_keys
        if fk.column.table.name == models.User.__tablename__
    }
    handled = {_column_key(column) for column in actions.USER_REFERENCES.values()} | LINK_TABLES

    assert referencing == handled


def test_everything_moves_to_destination(session: SyncSession, users):
    dst, src = users
    dst_email, dst_password, src_id = dst.email, dst.password, src.id
    _references(session, src)

    moved = {label: _ids_referencing(session, column, src_id) for label, column in actions.USER_REFERENCES.items()}
    assert all(moved.values()), [label for label, ids in moved.items() if not ids]

    _merge(session, dst, src)

    for label, column in actions.USER_REFERENCES.items():
        assert not _ids_referencing(session, column, src_id), label
        assert moved[label] <= _ids_referencing(session, column, dst.id), label
    for model in (models.links.ProjectAssigneeLink, models.links.SeqRequestAssigneeLink, models.links.UserAffiliation):
        assert session.scalar(sa.select(sa.func.count()).select_from(model).where(model.user_id == src_id)) == 0
        assert session.scalar(sa.select(sa.func.count()).select_from(model).where(model.user_id == dst.id)) == 1

    assert session.get(models.User, src_id) is None
    dst = session.get(models.User, dst.id)
    assert dst.email == dst_email
    assert dst.password == dst_password


def test_shared_assignments_are_not_duplicated(session: SyncSession, users):
    dst, src = users
    project = create_project(session, dst)
    seq_request = create_seq_request(session, dst)
    for user in (dst, src):
        session.add(models.links.ProjectAssigneeLink(project_id=project.id, user_id=user.id))
        session.add(models.links.SeqRequestAssigneeLink(seq_request_id=seq_request.id, user_id=user.id))
    session.flush()

    _merge(session, dst, src)

    assert [u.id for u in session.get(models.Project, project.id).assignees] == [dst.id]
    assert [u.id for u in session.get(models.SeqRequest, seq_request.id).assignees] == [dst.id]


@pytest.mark.parametrize("src_type, dst_type, expected", [
    (AffiliationType.OWNER, AffiliationType.MEMBER, AffiliationType.OWNER),
    (AffiliationType.MEMBER, AffiliationType.OWNER, AffiliationType.OWNER),
    (AffiliationType.MANAGER, AffiliationType.MEMBER, AffiliationType.MANAGER),
    (AffiliationType.MEMBER, AffiliationType.MANAGER, AffiliationType.MANAGER),
])
def test_shared_group_keeps_stronger_affiliation(session: SyncSession, users, src_type, dst_type, expected):
    dst, src = users
    group = create_group(session)
    session.add(Q.affiliation.create(user=src, group=group, type=src_type))
    session.add(Q.affiliation.create(user=dst, group=group, type=dst_type))
    session.flush()

    _merge(session, dst, src)

    affiliations = session.scalars(sa.select(models.links.UserAffiliation).where(
        models.links.UserAffiliation.group_id == group.id
    )).all()
    assert [(a.user_id, a.affiliation_type) for a in affiliations] == [(dst.id, expected)]
    if expected == AffiliationType.OWNER:
        assert session.get(models.Group, group.id).owner.id == dst.id


def test_other_groups_move(session: SyncSession, users):
    dst, src = users
    group = create_group(session)
    session.add(Q.affiliation.create(user=src, group=group, type=AffiliationType.OWNER))
    session.flush()

    _merge(session, dst, src)

    assert session.get(models.Group, group.id).owner.id == dst.id


@pytest.mark.parametrize("src_role, dst_role, expected", [
    (UserRole.BIOINFORMATICIAN, UserRole.CLIENT, UserRole.BIOINFORMATICIAN),
    (UserRole.CLIENT, UserRole.BIOINFORMATICIAN, UserRole.BIOINFORMATICIAN),
    (UserRole.TECHNICIAN, UserRole.BIOINFORMATICIAN, UserRole.BIOINFORMATICIAN),
    (UserRole.ADMIN, UserRole.TECHNICIAN, UserRole.ADMIN),
    (UserRole.DEACTIVATED, UserRole.CLIENT, UserRole.CLIENT),
    (UserRole.CLIENT, UserRole.DEACTIVATED, UserRole.CLIENT),
    (UserRole.TEMPORARY, UserRole.CLIENT, UserRole.CLIENT),
])
def test_destination_gets_higher_role(session: SyncSession, users, src_role, dst_role, expected):
    dst, src = users
    src.role, dst.role = src_role, dst_role
    session.flush()

    assert _merge(session, dst, src).role == expected


@pytest.mark.parametrize("src_offset, dst_offset, expected", [
    (timedelta(days=1), None, "src"),
    (None, timedelta(days=1), "dst"),
    (timedelta(days=1), timedelta(days=2), "src"),
    (timedelta(days=2), timedelta(days=1), "dst"),
])
def test_destination_keeps_later_last_login(session: SyncSession, users, src_offset, dst_offset, expected):
    dst, src = users
    now = datetime.now(timezone.utc)
    src.last_login = now - src_offset if src_offset else None
    dst.last_login = now - dst_offset if dst_offset else None
    session.flush()
    expected_login = src.last_login if expected == "src" else dst.last_login

    assert _merge(session, dst, src).last_login == expected_login


def test_passkeys_move_when_destination_has_no_handle(session: SyncSession, users):
    dst, src = users
    handle = src.webauthn_user_handle = os.urandom(32)
    passkey = _passkey(session, src)

    dst = _merge(session, dst, src)

    assert dst.webauthn_user_handle == handle
    assert [p.id for p in dst.passkeys] == [passkey.id]


def test_passkeys_deleted_when_destination_has_handle(session: SyncSession, users):
    dst, src = users
    src.webauthn_user_handle = os.urandom(32)
    dst_handle = dst.webauthn_user_handle = os.urandom(32)
    src_passkey, dst_passkey = _passkey(session, src), _passkey(session, dst)

    dst = _merge(session, dst, src)

    assert dst.webauthn_user_handle == dst_handle
    assert [p.id for p in dst.passkeys] == [dst_passkey.id]
    assert session.get(models.UserPasskey, src_passkey.id) is None


def test_same_user_is_rejected(session: SyncSession, users):
    dst, _ = users

    with pytest.raises(ValueError, match="cannot be the same"):
        actions.merge_users(session, user_dst=dst, user_src=dst)


def test_project_title_clash_is_rejected_before_any_change(session: SyncSession, users):
    dst, src = users
    title = str(uuid.uuid4())
    for user in (dst, src):
        project = create_project(session, user)
        project.title = title
    sample = create_sample(session, src, create_project(session, src))
    session.flush()

    with pytest.raises(ValueError, match=title):
        actions.merge_users(session, user_dst=dst, user_src=src)

    session.expire_all()
    assert session.get(models.User, src.id) is not None
    assert session.get(models.Sample, sample.id).owner_id == src.id


def test_preview(session: SyncSession, users):
    dst, src = users
    src.role, dst.role = UserRole.BIOINFORMATICIAN, UserRole.CLIENT
    create_project(session, src)
    create_project(session, src)
    group = create_group(session)
    session.add(Q.affiliation.create(user=src, group=group, type=AffiliationType.OWNER))
    session.add(Q.affiliation.create(user=dst, group=group, type=AffiliationType.MEMBER))
    session.add(Q.affiliation.create(user=src, group=create_group(session), type=AffiliationType.MEMBER))
    src.webauthn_user_handle = os.urandom(32)
    _passkey(session, src)
    session.flush()

    preview = actions.merge_users_preview(session, user_dst=dst, user_src=src)

    assert dict(preview.counts) == {"Projects": 2, "Group memberships": 1}
    assert preview.role == UserRole.BIOINFORMATICIAN
    assert preview.affiliation_upgrades == [(group.name, AffiliationType.OWNER)]
    assert preview.num_passkeys == 1 and preview.passkeys_move
    assert preview.conflicts == []
    assert session.get(models.User, src.id) is not None


def test_preview_reports_title_clash(session: SyncSession, users):
    dst, src = users
    for user in (dst, src):
        create_project(session, user).title = "same"
    session.flush()

    preview = actions.merge_users_preview(session, user_dst=dst, user_src=src)

    assert len(preview.conflicts) == 1 and "'same'" in preview.conflicts[0]
