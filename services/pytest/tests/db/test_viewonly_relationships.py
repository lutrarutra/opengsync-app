from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import orm

from opengsync_db import SyncSession, actions, models

from .create_units import create_user, create_project, create_seq_request, create_sample, create_library


# SQLAlchemy 2.1's selectinload no longer de-duplicates rows, so these many-to-many relationships
# over sample_library_link must not list an object twice when a sample/library is linked more than once.
LOADERS = [None, orm.selectinload, orm.joinedload, orm.subqueryload]


def _load(session: SyncSession, model: type[Any], id: int, attr: Any, loader) -> Any:
    q = sa.select(model).where(model.id == id).execution_options(populate_existing=True)
    if loader is not None:
        q = q.options(loader(attr))
    return session.execute(q).unique().scalar_one()


@pytest.fixture
def linked(session: SyncSession) -> dict[str, Any]:
    user = create_user(session)
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    other_request = create_seq_request(session, user)

    sample_a = create_sample(session, user, project)
    sample_b = create_sample(session, user, project)

    # Multiplexed: one library linked to two samples of the project.
    multiplexed = create_library(session, user, seq_request)
    actions.link_sample_library(session, sample_a.id, multiplexed.id)
    actions.link_sample_library(session, sample_b.id, multiplexed.id)

    # sample_a has a second library in the same request.
    second = create_library(session, user, seq_request)
    actions.link_sample_library(session, sample_a.id, second.id)

    # Unrelated request with its own sample, must not leak in.
    other_sample = create_sample(session, user, create_project(session, user))
    other_library = create_library(session, user, other_request)
    actions.link_sample_library(session, other_sample.id, other_library.id)

    return {
        "project": project, "seq_request": seq_request,
        "sample_a": sample_a, "sample_b": sample_b,
        "multiplexed": multiplexed, "second": second,
    }


@pytest.mark.parametrize("loader", LOADERS, ids=lambda x: x.__name__ if x else "lazy")
def test_project_libraries_are_distinct(session: SyncSession, linked: dict[str, Any], loader):
    project = _load(session, models.Project, linked["project"].id, models.Project.libraries, loader)
    assert [library.id for library in project.libraries] == sorted([linked["multiplexed"].id, linked["second"].id])


@pytest.mark.parametrize("loader", LOADERS, ids=lambda x: x.__name__ if x else "lazy")
def test_seq_request_samples_are_distinct(session: SyncSession, linked: dict[str, Any], loader):
    seq_request = _load(session, models.SeqRequest, linked["seq_request"].id, models.SeqRequest.samples, loader)
    assert sorted(sample.id for sample in seq_request.samples) == sorted([linked["sample_a"].id, linked["sample_b"].id])


@pytest.mark.parametrize("loader", LOADERS, ids=lambda x: x.__name__ if x else "lazy")
def test_sample_seq_requests_are_distinct(session: SyncSession, linked: dict[str, Any], loader):
    sample = _load(session, models.Sample, linked["sample_a"].id, models.Sample.seq_requests, loader)
    assert [seq_request.id for seq_request in sample.seq_requests] == [linked["seq_request"].id]


@pytest.mark.parametrize("loader", LOADERS, ids=lambda x: x.__name__ if x else "lazy")
def test_seq_request_sample_library_links(session: SyncSession, linked: dict[str, Any], loader):
    seq_request = _load(session, models.SeqRequest, linked["seq_request"].id, models.SeqRequest.sample_library_links, loader)
    assert sorted((link.sample_id, link.library_id) for link in seq_request.sample_library_links) == sorted([
        (linked["sample_a"].id, linked["multiplexed"].id),
        (linked["sample_b"].id, linked["multiplexed"].id),
        (linked["sample_a"].id, linked["second"].id),
    ])
