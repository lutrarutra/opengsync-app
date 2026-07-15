from fastapi import APIRouter, Depends, Query

from opengsync_db import models, SyncSession, queries as Q

from ...core import dependencies, responses

router = APIRouter(prefix="/sequencers", tags=["sequencers"])


@router.get("/search")
def search_sequencers(
    word: str | None = Query(None, description="Search word for sequencer name"),
    selected_id: int | None = Query(None, description="Currently selected sequencer"),
    current_user: models.User = Depends(dependencies.require_user),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.sequencer.select()

    if selected_id is not None and not word:
        stmt = Q.sequencer.select(id=selected_id, statement=stmt)
    elif word is not None:
        stmt = Q.sequencer.search(name=word, statement=stmt)

    sequencers, count = session.page(stmt, page=page)
    return responses.htmx_response(template="components/search/sequencer.html", sequencers=sequencers)
