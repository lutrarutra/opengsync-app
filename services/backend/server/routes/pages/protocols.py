from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/protocols", tags=["protocols"])


@router.get("/")
def protocols():
    return responses.html_response("protocols_page.html", title="Protocols")


@router.get("/{protocol_id}")
def protocol(protocol_id: int):
    # NOTE: Protocol lookup and breadcrumb resolution handled client-side.
    return responses.html_response(
        "protocol_page.html",
        protocol_id=protocol_id,
        title=f"Protocol {protocol_id}",
    )