from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import joinedload

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, exceptions as exc, responses
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])


class APITokenTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, sortable=True),
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
    user_id: int | None = Query(None, description="Optional owner user ID to filter tokens"),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = APITokenTable(route="render_api_token_table", page=page, order_by=order_by)
    stmt = Q.api_token.select(owner_id=user_id)

    if user_id is not None:
        if session.get_access_level(Q.user.permissions(user_id=user_id, viewer_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        # scoped as user_id (not owner_id) so it doesn't collide with the searchable owner_id column state
        table.url_params["user_id"] = user_id
        table.template = "components/tables/user-api_token.html"
        table.context["user"] = session.get_one(Q.user.select(id=user_id))
    else:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/api-token.html"

    tokens = table.paginate(
        session, stmt, page=page, order_by=order_by,
        options=[joinedload(models.APIToken.owner)],
    )
    return table.make_response(tokens=tokens)


@router.post("/{token_id}/deactivate")
def deactivate_api_token(
    token_id: int,
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    token = session.get_one(Q.api_token.select(id=token_id))
    if token.owner_id != current_user.id and not current_user.is_admin:
        raise exc.NoPermissionsException("You do not have permission to deactivate this API token.")

    token._expired = True
    session.save(token)
    return responses.htmx_response(flash=responses.flash("API token deactivated.", "success"))
