from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, AsyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/share_tokens", tags=["share_tokens"])


class ShareTokenTable(HTMXTable):
    columns = [
        TableCol(title="UUID", label="uuid", col_size=1, searchable=True, sortable=True),
        TableCol(title="Expiration", label="expiration", col_size=4),
        TableCol(title="Time Valid", label="time_valid_min", col_size=4),
        TableCol(title="Owner", label="owner", col_size=4, choices=C.DataPathType.as_selectable(), sortable=True, sort_by="owner_id"),
        TableCol(title="# Paths", label="num_paths", col_size=3, sortable=True),
    ]


@router.get("/render-table-page")
async def render_share_token_table(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    project_id: int | None = Query(None, description="Optional project ID to filter share tokens"),
    current_user: models.User = Depends(dependencies.require_insider),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.ShareToken, default=models.ShareToken.uuid.asc())),
    session: AsyncSession = Depends(dependencies.db_session),
):
    table = ShareTokenTable(route="render_share_token_table", page=page, order_by=order_by)

    stmt = Q.share_token.select()

    if project_id is not None:
        stmt = Q.share_token.select(project_id=project_id)
        table.url_params["project_id"] = project_id


    share_tokens, count = await session.page(
        stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.ShareToken.owner),
            orm.selectinload(models.ShareToken.paths),
            orm.with_expression(models.ShareToken._num_paths, models.ShareToken.num_paths.expression),
        ]
    )
    table.set_num_pages(count)

    return await responses.htmx_response(
        template="components/tables/share_token.html",
        share_tokens=share_tokens,
        table=table,
    )