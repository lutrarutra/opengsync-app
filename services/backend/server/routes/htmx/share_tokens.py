from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...core import dependencies
from ...components.tables import Table, TableState, Col, Text, Variant, related

router = APIRouter(prefix="/share_tokens", tags=["share_tokens"])


ST = models.ShareToken
_FULL_NAME = Q.search.full_name(models.User)


class ShareTokenTable(Table):
    key = "share"
    model = models.ShareToken
    noun = "share links"
    default_sort = ("created_utc", "desc")
    load = (
        orm.selectinload(ST.owner),
        orm.selectinload(ST.paths),
        orm.with_expression(ST._num_paths, ST.num_paths.expression),
    )
    columns = [
        Col("uuid", "UUID", search=Text(ST.uuid), hideable=False, size=1),
        Col("expiration", "Expiration", sort=True, size=4),
        Col(
            "owner", "Owner", sort=related(ST.owner, _FULL_NAME), size=4,
            search=Text(_FULL_NAME, models.User.email, via=ST.owner),
        ),
        Col("time_valid_min", "Time Valid", sort=True, size=4),
        Col("num_paths", "# Paths", sort=True, size=3),
        Col("created_utc", "Created", sort=True, display=False),
    ]
    variants = {
        "default": Variant(
            ["uuid", "expiration", "owner", "time_valid_min", "num_paths"], "components/tables/rows/share_token.html",
            dom_id="share_token-table",
        ),
    }

    tie_break = (ST.uuid.asc(),)  # the primary key is the uuid


@router.get("/render-table-page")
def render_share_token_table(
    project_id: int | None = Query(None, description="Optional project ID to filter share tokens"),
    state: TableState = Depends(ShareTokenTable.params),
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.share_token.select(project_id=project_id)
    table = ShareTokenTable(state, route="render_share_token_table", user=current_user)
    if project_id is not None:
        table.use("default", project_id=project_id)
    return table.render(session, stmt)
