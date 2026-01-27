import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class SequencerTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Model", label="model", col_size=2, choices=cats.SequencerModel.as_list(), sortable=True, sort_by="model_id"),
    ]
    

def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = SequencerTable(route="sequencers_htmx.get", page=request.args.get("page", 0, type=int))

    if (name := request.args.get("name")):
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
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
        if sort_by not in models.Sequencer.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (model_in := request.args.get("model_in")) is not None:
        model_in = json.loads(model_in)
        try:
            model_in = [cats.SequencerModel.get(int(model)) for model in model_in]
            if model_in:
                fnc_context["model_in"] = model_in
                table.filter_values["model"] = model_in
        except ValueError:
            raise exceptions.BadRequestException()

    context = parse_context(current_user, request) | kwargs

    sequencers, table.num_pages = db.sequencers.find(page=table.active_page, **fnc_context)

    context.update({
        "sequencers": sequencers,
        "template_name_or_list": "components/tables/sequencer.html",
        "table": table,
    })
    return context

def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    context = parse_context(current_user, request) | kwargs
    fnc_context = {}
    
    if not (field_name := request.args.get("field_name")):
        raise exceptions.BadRequestException("No search field provided.")
    
    if (selected_id := request.args.get(f"{field_name}-selected")) is not None:
        try:
            selected_id = int(selected_id)
            context["selected_id"] = selected_id
        except ValueError:
            pass
        
    context["field_name"] = field_name
    page = request.args.get("page", 0, type=int)
    
    if (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            fnc_context["name"] = name
        else:
            fnc_context["sort_by"] = "name"
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")
    
    if (group := context.get("group")) is not None:
        fnc_context["group_id"] = group.id
    else:
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id
    
    sequencers, num_pages = db.sequencers.find(page=page, **fnc_context)

    context.update({
        "sequencers": sequencers,
        "template_name_or_list": "components/search/sequencer.html",
        "num_pages": num_pages,
    })
    return context