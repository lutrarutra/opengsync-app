from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("/")
async def libraries():
    return await responses.html_response("libraries_page.html", title="Libraries")


@router.get("/{library_id}")
async def library(
    library_id: int,
    current_user: models.User = Depends(dependencies.require_user),
):
    # NOTE: Library lookup, access checks, form generation, and
    # breadcrumb resolution are handled client-side via API calls.
    return await responses.html_response(
        "library_page.html",
        library_id=library_id,
        title=f"Library #{library_id:04d}",
    )