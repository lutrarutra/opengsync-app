from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class APITokenTable(HTMXTable):
    columns = [
        TableCol(title="Expiration", label="expiration", col_size=3, sortable=True),
        TableCol(title="Owner", label="owner_id", col_size=3, searchable=True, sortable=True),
        TableCol(title="Valid Min.", label="time_valid_min", col_size=3, sortable=True),
    ]    

def get_table_context(current_user: models.User, request: Request, user: models.User, **kwargs) -> dict:
    fnc_context = {}
    table = APITokenTable(route="users_htmx.get_api_tokens", page=request.args.get("page", 0, type=int))
    table.url_params["user_id"] = user.id
    context = parse_context(current_user, request) | kwargs
    
    if user.id != current_user.id and not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    tokens, table.num_pages = db.api_tokens.find(
        page=table.active_page, owner=user, **fnc_context
    )

    context.update({
        "tokens": tokens,
        "template_name_or_list": "components/tables/user-api_token.html",
        "table": table,
        "user": user,
    })
    return context