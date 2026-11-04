"""Search relevance must not be NULL for rows with an optional column (insider test 2026-11-04).

The project picker searches title and identifier with the same word and orders by the summed similarity;
a project without identifier had a NULL relevance and sorted after every weaker match (nulls last).
"""
from opengsync_db import SyncSession, queries as Q

from .create_units import create_user


def test_project_without_identifier_ranks_by_title(session: SyncSession):
    owner = create_user(session)
    target = session.save(Q.project.create(title="Carol Project", description="", owner_id=owner.id), flush=True)
    for i, title in enumerate(["Carousel screen", "Coral reef", "Card stock"]):
        p = session.save(Q.project.create(title=title, description="", owner_id=owner.id), flush=True)
        p.identifier = f"BSA_{9000 + i}"
    session.flush()

    ranked = session.get_all(Q.project.search(title="Carol Project", identifier="Carol Project"), limit=None)
    assert ranked[0].id == target.id
    ranked = session.get_all(Q.project.search(title="Carol", identifier="Carol"), limit=None)
    assert ranked[0].id == target.id
