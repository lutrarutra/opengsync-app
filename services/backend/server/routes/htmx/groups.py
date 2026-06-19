from fastapi import APIRouter, Depends, Query

from opengsync_db import models, AsyncSession, queries as Q

from ...core import dependencies, responses


router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("/search")
async def search_groups(
    word: str = Query(..., description="Search word for group name"),
    selected_id: int | None = Query(None, description="Currently selected group"),
    current_user: models.User = Depends(dependencies.require_user),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: AsyncSession = Depends(dependencies.db_session),
):
    stmt = Q.group.search(name=word)

    if selected_id is not None and not word:
        stmt = Q.group.select(id=selected_id, statement=stmt)

    if not current_user.is_insider():
        stmt = Q.group.select(user_id=current_user.id, statement=stmt)

    groups, count = await session.page(stmt, page=page)
    return await responses.htmx_response(template="components/search/group.html", groups=groups)
