from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/")
async def users_page(
    current_user: models.User = Depends(dependencies.require_insider),
):
    return await responses.html_response("users_page.html", title="Users")


@router.get("/{user_id}")
async def user_page(
    user_id: int,
    current_user: models.User = Depends(dependencies.require_user),
):
    # Non-insiders can only view their own profile
    if not current_user.is_insider() and user_id != current_user.id:
        raise exceptions.PermissionDeniedException()

    # NOTE: User lookup, projects/requests queries, and breadcrumb
    # resolution are handled client-side via API calls.
    return await responses.html_response(
        "user_page.html",
        user_id=user_id,
        title=f"User {user_id}",
    )