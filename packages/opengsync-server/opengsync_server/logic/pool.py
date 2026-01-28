import json
from typing import cast

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class PoolTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=2, choices=cats.LibraryType.as_list()),
        TableCol(title="Status", label="status", col_size=2, sortable=True, sort_by="status_id", choices=cats.PoolStatus.as_list()),
        TableCol(title="Type", label="type", col_size=1, sortable=True, sort_by="type_id", choices=cats.PoolType.as_list()),
        TableCol(title="Owner", label="owner", col_size=2, search_type="text"),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = PoolTable(route="pools_htmx.get", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs
    
    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [cats.PoolStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (type_in := request.args.get("type_in")):
        type_in = json.loads(type_in)
        try:
            type_in = [cats.PoolType.get(int(type)) for type in type_in]
            if type_in:
                fnc_context["type_in"] = type_in
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (library_types_in := request.args.get("library_types_in")):
        library_types_in = json.loads(library_types_in)
        try:
            library_types_in = [cats.LibraryType.get(int(library_type)) for library_type in library_types_in]
            if library_types_in:
                fnc_context["library_types_in"] = library_types_in
                table.filter_values["library_types"] = library_types_in
        except ValueError:
            raise exceptions.BadRequestException()

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
    elif (owner := request.args.get("owner")):
        fnc_context["owner"] = owner
        table.active_search_var = "owner"
        table.active_query_value = owner

    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.Pool.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-pool.html"        
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id
    elif (experiment := context.get("experiment")) is not None:   
        experiment = cast(models.Experiment, experiment)
        template = "components/tables/experiment-pool.html" 
        fnc_context["experiment_id"] = experiment.id
        table.url_params["experiment_id"] = experiment.id
        table.active_page = None
        fnc_context["limit"] = None

        context["can_edit_pooling"] = (
            (
                current_user.is_insider() and
                experiment.status == cats.ExperimentStatus.DRAFT and 
                not experiment.workflow.combined_lanes
            ) or 
            (
                current_user.is_admin() and not experiment.workflow.combined_lanes
            )
        )
            

    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-pool.html"
        fnc_context["lab_prep_id"] = lab_prep.id
        table.url_params["lab_prep_id"] = lab_prep.id
    else:
        template = "components/tables/pool.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id

    pools, table.num_pages = db.pools.find(page=table.active_page, **fnc_context)
        
    context.update({
        "pools": pools,
        "template_name_or_list": template,
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
    
    pools, num_pages = db.pools.find(page=page, **fnc_context)

    context.update({
        "pools": pools,
        "template_name_or_list": "components/search/pool.html",
        "num_pages": num_pages,
    })
    return context