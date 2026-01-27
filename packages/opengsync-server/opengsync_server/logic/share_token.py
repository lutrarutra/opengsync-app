import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context


class ShareTokenTable(HTMXTable):
    columns = [
        TableCol(title="UUID", label="uuid", col_size=1, search_type="number", sortable=True),
        TableCol(title="Expiration", label="expiration", col_size=4),
        TableCol(title="Time Valid", label="time_valid_min", col_size=4),
        TableCol(title="Owner", label="owner", col_size=4, choices=cats.DataPathType.as_list(), sortable=True, sort_by="owner_id"),
        TableCol(title="# Paths", label="num_paths", col_size=3, sortable=True),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = ShareTokenTable(route="share_htmx.get_share_tokens", page=request.args.get("page", 0, type=int))

    if (path := request.args.get("path")):
        fnc_context["path"] = path
        table.active_search_var = "path"
        table.active_query_value = path
    elif (id_ := request.args.get("id")):
        try:
            id_ = int(id_)
            fnc_context["id"] = id_
            table.active_search_var = "id"
            table.active_query_value = str(id_)
        except ValueError:
            raise exceptions.BadRequestException()
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.ShareToken.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [cats.DataPathType.get(int(t)) for t in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    context = parse_context(current_user, request) | kwargs
    share_tokens, table.num_pages = db.shares.find(page=table.active_page, **fnc_context)

    context.update({
        "share_tokens": share_tokens,
        "template_name_or_list": "components/tables/share_token.html",
        "table": table,
    })
    return context