from fastapi import APIRouter, Depends

from opengsync_db import SyncSession, queries as Q

from ...core import dependencies, responses

router = APIRouter(prefix="/sequencers", tags=["sequencers"])


@router.get("/")
def sequencers_page():
    return responses.html_response("sequencers_page.html", title="Sequencers")


@router.get("/{sequencer_id}")
def sequencer_page(
    sequencer_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    sequencer = session.get_one(Q.sequencer.select(id=sequencer_id))
    return responses.html_response(
        "sequencer_page.html",
        sequencer=sequencer,
        title=f"{sequencer.name}",
    )