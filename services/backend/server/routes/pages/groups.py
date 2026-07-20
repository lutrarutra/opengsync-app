from fastapi import APIRouter, Depends

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("/")
def groups_page():
    return responses.html_response("groups_page.html", title="Groups")


@router.get("/{group_id}")
def group_page(
    group_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.group_permissions),
):
    group = session.get_one(Q.group.select(id=group_id))

    return responses.html_response(
        "group_page.html",
        group=group,
        title=f"Group {group_id}",
        access_level=access_level,
    )