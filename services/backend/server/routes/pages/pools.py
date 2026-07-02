from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(prefix="/pools", tags=["pools"])


@router.get("/")
def pools_page():
    return responses.html_response("pools_page.html", title="Pools")


@router.get("/{pool_id}")
def pool_page(
    pool_id: int,
    current_user: models.User = Depends(dependencies.require_user),
):
    # NOTE: Pool lookup, access checks, editability, indexing checks,
    # and breadcrumb resolution are handled client-side via API calls.
    return responses.html_response(
        "pool_page.html",
        pool_id=pool_id,
        title=f"Pool {pool_id}",
    )