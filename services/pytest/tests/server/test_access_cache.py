"""Cached access levels (access:<model>:<id>:user:<viewer>) must not outlive the change that revokes them.

Regression for the customer test 2026-11-04: a member removed from a group could still add share
emails to and delete the group's request for 5 minutes, and a request owner kept WRITE after the
request left DRAFT.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import access_cache, dependencies

from ..db.create_units import create_user, create_seq_request, create_group, create_project, create_sample
from ._http import get, post_form, delete


def _cached_keys(client: TestClient, pattern: str) -> list[str]:
    from redis import Redis
    with Redis(connection_pool=client.app.state.redis_pool) as r:
        return [k.decode() if isinstance(k, bytes) else k for k in r.scan_iter(match=pattern)]


# ── listener: which key patterns a committed change makes stale ───────────────


def _committed(session: SyncSession, change) -> set[str]:
    session.commit()
    access_cache.pop_patterns(session)
    change()
    session.flush()
    session.commit()
    return access_cache.pop_patterns(session)


def test_seq_request_status_change_drops_request_and_children(session: SyncSession):
    seq_request = create_seq_request(session, create_user(session))

    def change():
        seq_request.status = C.SeqRequestStatus.SUBMITTED

    assert _committed(session, change) >= {
        f"access:seq_request:{seq_request.id}:*", "access:library:*", "access:pool:*", "access:media_file:*",
    }


def test_project_owner_change_drops_project_and_samples(session: SyncSession):
    project = create_project(session, create_user(session))
    other = create_user(session)

    def change():
        project.owner_id = other.id

    assert _committed(session, change) >= {f"access:project:{project.id}:*", "access:sample:*"}


def test_sample_status_change(session: SyncSession):
    user = create_user(session)
    sample = create_sample(session, user, create_project(session, user))

    def change():
        sample.status = C.SampleStatus.REJECTED

    assert f"access:sample:{sample.id}:*" in _committed(session, change)


def test_affiliation_insert_and_delete_drop_the_users_levels(session: SyncSession):
    user, group = create_user(session), create_group(session)
    affiliation = None

    def add():
        nonlocal affiliation
        affiliation = session.save(Q.affiliation.create(user=user, group=group, type=C.AffiliationType.MEMBER))

    assert _committed(session, add) >= {f"access:*:user:{user.id}", f"access:group:{group.id}:*"}
    assert _committed(session, lambda: session.delete(affiliation)) >= {f"access:*:user:{user.id}"}


def test_role_change_drops_users_levels_and_cached_user(session: SyncSession):
    user = create_user(session)

    def change():
        user.role = C.UserRole.DEACTIVATED

    assert _committed(session, change) >= {f"access:*:user:{user.id}", f"user:{user.id}"}


def test_unrelated_change_and_rollback_record_nothing(session: SyncSession):
    seq_request = create_seq_request(session, create_user(session))

    def rename():
        seq_request.name = "renamed"

    assert _committed(session, rename) == set()

    session.commit()
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.flush()
    session.rollback()
    assert access_cache.pop_patterns(session) == set()


def test_every_cached_namespace_is_invalidated():
    """A new cached *_permissions dependency must get invalidation rules in core/access_cache.py."""
    source = Path(dependencies.__file__).read_text()
    namespaces = set(re.findall(r'f"access:(\w+):\{', source))
    assert namespaces, "cache key format changed; update this test"
    assert namespaces <= access_cache.INVALIDATED_NAMESPACES


# ── end to end through the routes ─────────────────────────────────────────────


@pytest.fixture
def group_request(session: SyncSession, user, user_2):
    group = create_group(session)
    session.save(Q.affiliation.create(user=user, group=group, type=C.AffiliationType.OWNER))
    session.save(Q.affiliation.create(user=user_2, group=group, type=C.AffiliationType.MEMBER))
    seq_request = create_seq_request(session, user)
    seq_request.group_id = group.id
    session.save(seq_request, flush=True)
    session.commit()
    return group, seq_request


def test_removed_member_loses_access_immediately(
    client: TestClient, session: SyncSession, user, user_2, user_token: str, user_2_token: str, group_request,
):
    group, seq_request = group_request
    assert get(client, f"/seq_requests/{seq_request.id}", user_2_token).status_code == 200
    assert _cached_keys(client, f"access:seq_request:{seq_request.id}:user:{user_2.id}")

    assert delete(client, f"/htmx/groups/{group.id}/remove-user/{user_2.id}", user_token).status_code == 204

    assert not _cached_keys(client, f"access:*:user:{user_2.id}")
    assert get(client, f"/seq_requests/{seq_request.id}", user_2_token).status_code == 403
    response = post_form(client, f"/htmx/seq_requests/{seq_request.id}/share-email", {"email": "x@example.com"}, user_2_token)
    assert response.status_code == 403
    assert delete(client, f"/htmx/seq_requests/{seq_request.id}/delete", user_2_token).status_code == 403
    session.expire_all()
    assert session.get(models.SeqRequest, seq_request.id) is not None


def test_owner_loses_write_when_request_leaves_draft(
    client: TestClient, session: SyncSession, user, user_token: str,
):
    seq_request = create_seq_request(session, user)
    session.commit()
    begin = f"/htmx/workflows/library-annotation/{seq_request.id}/begin"
    assert get(client, begin, user_token, htmx=True).status_code == 200  # caches WRITE

    assert post_form(client, f"/htmx/seq_requests/{seq_request.id}/archive", {}, user_token).status_code in (200, 204)

    assert get(client, begin, user_token, htmx=True).status_code == 403
    assert get(client, f"/htmx/workflows/sample-submission-layout/{seq_request.id}/begin", user_token, htmx=True).status_code == 403
