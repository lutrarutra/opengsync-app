from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("/")
async def groups():
    return await responses.html_response("groups_page.html", title="Groups")


@router.get("/{group_id}")
async def group(
    group_id: int,
    current_user: models.User = Depends(dependencies.require_user),
):
    # NOTE: Group lookup, affiliation checks, form generation, and
    # breadcrumb resolution are handled client-side via API calls.
    return await responses.html_response(
        "group_page.html",
        group_id=group_id,
        title=f"Group {group_id}",
    )