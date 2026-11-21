from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import joinedload

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, exceptions as exc, responses, query_options
from ...components.tables import Table, TableState, Col, Text, Exact, Entity, Variant, related

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])


T = models.APIToken
_FULL_NAME = Q.search.full_name(models.User)


class APITokenTable(Table):
    key = "tok"
    model = models.APIToken
    noun = "tokens"
    load = (joinedload(T.owner),)
    columns = [
        Col("id", "ID", sort=True, search=Exact(T.id), hideable=False, size=1),
        Col("token", "Token", hideable=False, size=1),
        Col(
            "owner", "Owner", sort=related(T.owner, _FULL_NAME), size=2,
            search=Text(_FULL_NAME, models.User.email, via=T.owner),
            filter=Entity(models.User, via=T.owner, option=query_options.user_option, search=(_FULL_NAME, models.User.email)),
        ),
        Col("time_valid_min", "Valid (min)", sort=True, size=1),
        Col("created_utc", "Created", sort=True, size=2),
        Col("expiration", "Expiration", sort=True, size=2),
    ]
    variants = {
        "default": Variant(
            ["id", "owner", "time_valid_min", "created_utc", "expiration"], "components/tables/rows/api-token.html",
            dom_id="api-token-table",
        ),
        "user": Variant(
            ["token", "expiration", "owner", "time_valid_min"], "components/tables/rows/user-api_token.html",
            dom_id="user-api_token-table", actions=True, toolbar="components/tables/toolbars/user-api_token.html", fields=["id", "time_valid_min", "created_utc", "expiration"],
        ),
    }


@router.get("/render-table-page")
def render_api_token_table(
    user_id: int | None = Query(None, description="Optional owner user ID to filter tokens"),
    state: TableState = Depends(APITokenTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.api_token.select(owner_id=user_id)
    table = APITokenTable(state, route="render_api_token_table", user=current_user)

    if user_id is not None:
        if (access_level := session.get_access_level(Q.user.permissions(user_id=user_id, viewer_id=current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.use("user", user_id=user_id, user=session.get_one(Q.user.select(id=user_id)))
        table.context["access_level"] = access_level
    elif not current_user.is_insider:
        raise exc.NoPermissionsException("You do not have permission to view this resource.")

    return table.render(session, stmt)


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
