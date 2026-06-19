import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class SequencerTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Model", label="model", col_size=2, choices=C.SequencerModel.as_selectable(), sortable=True, sort_by="model_id"),
    ]
    

def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = SequencerTable(route="sequencers_htmx.get", page=request.args.get("page", 0, type=int))
    stmt = sa.select(models.Sequencer)

    if (name := request.args.get("name")):
        stmt = Q.sequencer.search(name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.sequencer.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.Sequencer, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (model_in := request.args.get("model_in")) is not None:
        model_in = json.loads(model_in)
        try:
            model_in = [C.SequencerModel.get(int(model)) for model in model_in]
            if model_in:
                stmt = Q.sequencer.select(model_in=model_in, statement=stmt)
                table.filter_values["model"] = model_in
        except ValueError:
            raise exceptions.BadRequestException()

    context = parse_context(current_user, request) | kwargs

    sequencers, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)

    context.update({
        "sequencers": sequencers,
        "template_name_or_list": "components/tables/sequencer.html",
        "table": table,
    })
    return context

def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    context = parse_context(current_user, request) | kwargs
    page = request.args.get("page", 0, type=int)
    stmt = sa.select(models.Sequencer)
    
    if (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            stmt = Q.sequencer.search(name=name, statement=stmt)
        else:
            stmt = stmt.order_by(models.Sequencer.name.desc())
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")
    
    sequencers, count = db.session.page(stmt, page=page)

    context.update({
        "sequencers": sequencers,
        "template_name_or_list": "components/search/sequencer.html",
    })
    return context