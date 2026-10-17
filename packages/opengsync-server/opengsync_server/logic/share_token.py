import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context


class ShareTokenTable(HTMXTable):
    columns = [
        TableCol(title="UUID", label="uuid", col_size=1, searchable=True, sortable=True),
        TableCol(title="Expiration", label="expiration", col_size=4),
        TableCol(title="Time Valid", label="time_valid_min", col_size=4),
        TableCol(title="Owner", label="owner", col_size=4, choices=C.DataPathType.as_selectable(), sortable=True, sort_by="owner_id"),
        TableCol(title="# Paths", label="num_paths", col_size=3, sortable=True),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = ShareTokenTable(route="share_htmx.get_share_tokens", page=request.args.get("page", 0, type=int))
    stmt = sa.select(models.ShareToken)

    if (path := request.args.get("path")):
        raise NotImplementedError("Search by path is not implemented yet")
        table.active_search_var = "path"
        table.active_query_value = path
    elif (uuid := request.args.get("uuid")):
        table.active_search_var = "uuid"
        table.active_query_value = str(uuid)
        stmt = Q.share_token.select(uuid=uuid, statement=stmt)
    else:
        sort_by = request.args.get("sort_by", "uuid")
        sort_order = request.args.get("sort_order", "asc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.ShareToken, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [C.DataPathType.get(int(t)) for t in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    context = parse_context(current_user, request) | kwargs
    share_tokens, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)

    context.update({
        "share_tokens": share_tokens,
        "template_name_or_list": "components/tables/share_token.html",
        "table": table,
    })
    return context