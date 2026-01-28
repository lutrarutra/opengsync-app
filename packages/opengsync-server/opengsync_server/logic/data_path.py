import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context


class DataPathTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Path", label="path", col_size=4, search_type="text", sortable=True),
        TableCol(title="Type", label="type", col_size=2, choices=cats.DataPathType.as_list(), sortable=True, sort_by="type_id"),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = DataPathTable(route="share_htmx.get_data_paths", page=request.args.get("page", 0, type=int))

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
        if sort_by not in models.DataPath.sortable_fields:
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

    if (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-data_path.html"        
        fnc_context["experiment_id"] = experiment.id
        table.url_params["experiment_id"] = experiment.id
    elif (library := context.get("library")) is not None:
        template = "components/tables/library-data_path.html"        
        fnc_context["library_id"] = library.id
        table.url_params["library_id"] = library.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-data_path.html"        
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id
    elif (project := context.get("project")) is not None:
        template = "components/tables/project-data_path.html"        
        fnc_context["project_id"] = project.id
        table.url_params["project_id"] = project.id
    else:
        raise exceptions.BadRequestException("Experiment context is required to view sequencers.")

    data_paths, table.num_pages = db.data_paths.find(page=table.active_page, **fnc_context)

    context.update({
        "data_paths": data_paths,
        "template_name_or_list": template,
        "table": table,
    })
    return context