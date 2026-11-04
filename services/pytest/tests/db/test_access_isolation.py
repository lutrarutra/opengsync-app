"""Cross-customer isolation for every Q.<model>.permissions query.

Two customers each own a full set of objects. B also owns one of every kind, so a permission rule that
asks "does the viewer own *some* object" (an uncorrelated subquery) instead of "this object" grants B
access to A's objects and fails here. New models with a `permissions` query are picked up automatically.
"""
import inspect

import pytest

from opengsync_db import SyncSession, queries as Q, categories as C

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library, create_pool,
    create_group, create_file,
)


def _world(session: SyncSession, owner) -> dict[str, int]:
    group = create_group(session)
    session.save(Q.affiliation.create(user=owner, group=group, type=C.AffiliationType.OWNER), flush=True)
    project = create_project(session, owner)
    project.group_id = group.id
    seq_request = create_seq_request(session, owner)
    seq_request.group_id = group.id
    session.save(project, flush=True)
    session.save(seq_request, flush=True)
    return {
        "group": group.id,
        "project": project.id,
        "sample": create_sample(session, owner, project).id,
        "seq_request": seq_request.id,
        "library": create_library(session, owner, seq_request).id,
        "pool": create_pool(session, owner, seq_request).id,
        "media_file": create_file(session, seq_request=seq_request, uploader=owner).id,
        "user": owner.id,
    }


def _permission_modules() -> list[str]:
    return sorted(
        name for name in dir(Q)
        if not name.startswith("_") and callable(getattr(getattr(Q, name), "permissions", None))
    )


def _statement(model: str, object_id: int, viewer_id: int):
    fn = getattr(Q, model).permissions
    params = list(inspect.signature(fn).parameters)
    if model == "user":  # permissions(user_id, viewer_id)
        return fn(user_id=object_id, viewer_id=viewer_id)
    target = next(p for p in params if p != "user_id")
    return fn(**{target: object_id, "user_id": viewer_id})


def test_every_permissions_module_is_covered():
    worlds_cover = {"group", "project", "sample", "seq_request", "library", "pool", "media_file", "user"}
    assert set(_permission_modules()) <= worlds_cover, "add the new model to _world()"


@pytest.mark.parametrize("model", _permission_modules())
def test_other_customer_has_no_access(session: SyncSession, model: str):
    a, b = create_user(session), create_user(session)
    world_a = _world(session, a)
    world_b = _world(session, b)

    assert session.get_access_level(_statement(model, world_a[model], b.id)) == C.AccessLevel.NONE
    assert session.get_access_level(_statement(model, world_b[model], a.id)) == C.AccessLevel.NONE
    # sanity: each owner does have access to their own object
    assert session.get_access_level(_statement(model, world_a[model], a.id)) > C.AccessLevel.NONE
