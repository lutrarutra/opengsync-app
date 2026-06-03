from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(prefix="/seq_requests", tags=["seq_requests"])

@router.get("/")
async def seq_requests():  
    return await responses.html_response("seq_requests_page.html", title="Requests")


@router.get("/{seq_request_id}")
async def seq_request_page(
    seq_request_id: int,
    current_user: models.User = Depends(dependencies.require_user),
):
    # NOTE: Seq request lookup, access checks, submit/review checklists,
    # and breadcrumb resolution are handled client-side via API calls.
    return await responses.html_response(
        "seq_request_page.html",
        seq_request_id=seq_request_id,
        title=f"Request {seq_request_id}",
    )