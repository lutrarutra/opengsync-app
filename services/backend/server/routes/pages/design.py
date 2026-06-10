from fastapi import APIRouter, Depends

from opengsync_db import models, categories as C

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/design", tags=["design"])


@router.get("/")
async def design():
    # NOTE: FlowCellDesign queries require a DB session.
    # These counts will be populated by the frontend via API calls.
    return await responses.html_response(
        "design_page.html",
        title="Design",
    )