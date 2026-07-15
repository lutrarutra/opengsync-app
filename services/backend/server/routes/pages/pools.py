from fastapi import APIRouter, Depends
from sqlalchemy import orm

from opengsync_db import models, categories as C, queries as Q, SyncSession

from ...core import dependencies, responses

router = APIRouter(prefix="/pools", tags=["pools"])


@router.get("/")
def pools_page():
    return responses.html_response("pools_page.html", title="Pools")


@router.get("/{pool_id}", dependencies=[Depends(dependencies.pool_permissions)])
def pool_page(
    pool_id: int,
    current_user: models.User = Depends(dependencies.require_user),
    path_list: list = Depends(dependencies.parse_from_page),
    session: SyncSession = Depends(dependencies.db_session)
):
    pool = session.get_one(Q.pool.select(id=pool_id).options(
        orm.selectinload(models.Pool.libraries)
    ))

    is_editable = pool.status == C.PoolStatus.DRAFT or current_user.is_insider
    is_indexed = True and len(pool.libraries) > 0
    for library in pool.libraries:
        if not library.is_indexed:
            is_indexed = False
            break

    return responses.html_response(
        "pool_page.html", pool=pool, path_list=path_list, is_editable=is_editable,
        is_plated=False, is_indexed=is_indexed, title=f"Pool: {pool.name}"
    )