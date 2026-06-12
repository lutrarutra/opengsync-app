import json
from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context


class DilutionTable(HTMXTable):
    columns = [
        TableCol(title="Identifier", label="identifier", col_size=1, sortable=True),
        TableCol(title="Operator", label="operator", col_size=2),
        TableCol(title="Time", label="timestamp_utc", col_size=2),
        TableCol(title="Pool", label="pool_id", col_size=3, sortable=True),
        TableCol(title="Operator", label="operator_id", col_size=3),
        TableCol(title="Qubit Concentration", label="qubit_concentration", col_size=2),
        TableCol(title="Molarity", label="molarity", col_size=2),
        TableCol(title="Volume (uL)", label="volume_ul", col_size=2),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = DilutionTable(route="", page=None)
    stmt = sa.select(models.PoolDilution)

    if (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.pool_dilution.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "pool_id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.PoolDilution, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    context = parse_context(current_user, request) | kwargs

    if (pool := context.get("pool")) is not None:
        template = "components/tables/pool-dilution.html"
        stmt = Q.pool_dilution.select(pool=pool, statement=stmt)
        table.url_params["pool_id"] = pool.id
        table.route = "pools_htmx.get_dilutions"
    elif (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-pool-dilution.html"        
        stmt = Q.pool_dilution.select(experiment=experiment, statement=stmt)
        table.url_params["experiment_id"] = experiment.id
        table.route = "render_experiment_table_dilutions"
    else:
        raise exceptions.BadRequestException("No pool or experiment context provided for dilution table.")
    
    dilutions, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)
    
    context.update({
        "dilutions": dilutions,
        "template_name_or_list": template,
        "table": table,
    })
    return context