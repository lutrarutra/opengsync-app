from fastapi import APIRouter, Depends

from opengsync_db import SyncSession, queries as Q

from ...core import dependencies, responses

router = APIRouter(prefix="/protocols", tags=["protocols"])


@router.get("/")
def protocols_page():
    return responses.html_response("protocols_page.html", title="Protocols")


@router.get("/{protocol_id}")
def protocol_page(
    protocol_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    protocol = session.get_one(Q.protocol.select(id=protocol_id))
    return responses.html_response(
        "protocol_page.html",
        protocol=protocol,
        title=f"Protocol {protocol.name}",
    )