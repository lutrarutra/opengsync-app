from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/lab_preps", tags=["lab_preps"])


@router.get("/")
async def lab_preps():
    return await responses.html_response("lab_preps_page.html", title="Preps")


@router.get("/{lab_prep_id}")
async def lab_prep(lab_prep_id: int):
    # NOTE: Lab prep lookup, checklist, and breadcrumb resolution
    # are handled client-side via API calls.
    return await responses.html_response(
        "lab_prep_page.html",
        lab_prep_id=lab_prep_id,
        title=f"Prep {lab_prep_id}",
    )