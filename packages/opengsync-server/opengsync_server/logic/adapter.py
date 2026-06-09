from flask import Request
import sqlalchemy as sa

from opengsync_db import models
from opengsync_db import queries as Q

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class AdapterTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Well", label="well", col_size=3, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=2, sortable=True),
        TableCol(title="Name i7", label="name_i7", col_size=2),
        TableCol(title="Name i5", label="name_i5", col_size=2),
        TableCol(title="Sequence i7", label="sequence_i7", col_size=2),
        TableCol(title="Sequence i5", label="sequence_i5", col_size=2),
        TableCol(title="Sequence 1", label="sequence_1", col_size=2),
        TableCol(title="Sequence 2", label="sequence_2", col_size=2),
        TableCol(title="Sequence 3", label="sequence_3", col_size=2),
        TableCol(title="Sequence 4", label="sequence_4", col_size=2),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:    
    table = AdapterTable(route="adapters_htmx.get", page=request.args.get("page", 0, type=int))
    stmt = sa.select(models.Adapter)

    if (name := request.args.get("name")):
        stmt = Q.adapter.select(search_name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (well := request.args.get("well")):
        stmt = Q.adapter.select(well=well, statement=stmt)
        table.active_search_var = "well"
        table.active_query_value = well
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.adapter.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.Adapter, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    context = parse_context(current_user, request) | kwargs

    if (index_kit := context.get("index_kit")) is not None:
        template = "components/tables/index_kit-adapter.html"  
        table.route = "index_kits_htmx.get_adapters"      
        stmt = Q.adapter.select(index_kit_id=index_kit.id, statement=stmt)
        table.url_params["index_kit_id"] = index_kit.id
    else:
        template = "components/tables/adapter.html"

    adapters, table.num_pages = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(table.num_pages)
    
    context.update({
        "adapters": adapters,
        "template_name_or_list": template,
        "table": table,
    })
    return context