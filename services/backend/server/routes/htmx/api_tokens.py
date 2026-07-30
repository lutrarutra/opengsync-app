from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import joinedload

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])


class APITokenTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, sortable=True),
        TableCol(title="UUID", label="uuid", col_size=3),
        TableCol(title="Owner", label="owner_id", col_size=2, searchable=True, sortable=True),
        TableCol(title="Valid (min)", label="time_valid_min", col_size=1, sortable=True),
        TableCol(title="Created", label="created_utc", col_size=2, sortable=True),
        TableCol(title="Expiration", label="expiration", col_size=2, sortable=True),
    ]


@router.get("/render-table-page")
def render_api_token_table(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.APIToken, default=models.APIToken.id.desc())),
    owner_id: int | None = Query(None, description="Optional owner user ID to filter tokens"),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = APITokenTable(route="render_api_token_table", page=page, order_by=order_by)

    stmt = Q.api_token.select(
        owner_id=owner_id,
    )

    if owner_id is not None:
        if session.get_access_level(Q.user.permissions(user_id=owner_id, viewer_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.url_params["owner_id"] = owner_id
        table.template = "components/tables/user-api_token.html"
        table.context["user"] = session.get_one(Q.user.select(id=owner_id))
    else:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/api_token.html"

    tokens, count = session.page(
        stmt, page=page, order_by=order_by,
        options=[
            joinedload(models.APIToken.owner),
        ]
    )
    table.set_num_pages(count)
    return table.make_response(tokens=tokens)

