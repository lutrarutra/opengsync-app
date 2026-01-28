import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class ExperimentTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=2, search_type="text", sortable=True),
        TableCol(title="Workflow", label="workflow", col_size=2, choices=cats.ExperimentWorkFlow.as_list(), sortable=True, sort_by="workflow_id"),
        TableCol(title="Status", label="status", col_size=2, choices=cats.ExperimentStatus.as_list(), sortable=True, sort_by="status_id"),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=3, choices=cats.LibraryType.as_list()),
        TableCol(title="Operator", label="operator", col_size=2, search_type="text"),
        TableCol(title="Created", label="timestamp_created", col_size=2, sortable=True, sort_by="timestamp_created_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permission to view this resource.")
    
    fnc_context = {}
    table = ExperimentTable(route="experiments_htmx.get", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs

    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [cats.ExperimentStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()  
    
    if (workflow_in := request.args.get("workflow_in")):
        workflow_in = json.loads(workflow_in)
        try:
            workflow_in = [cats.ExperimentWorkFlow.get(int(workflow)) for workflow in workflow_in]
            if workflow_in:
                fnc_context["workflow_in"] = workflow_in
                table.filter_values["workflow"] = workflow_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")):
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (operator := request.args.get("operator")):
        fnc_context["operator"] = operator
        table.active_search_var = "operator"
        table.active_query_value = operator
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
        if sort_by not in models.Experiment.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (project := context.get("project")) is not None:
        template = "components/tables/project-experiment.html"        
        fnc_context["project_id"] = project.id
        table.url_params["project_id"] = project.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-experiment.html"        
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id
    else:
        template = "components/tables/experiment.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id   

    experiments, table.num_pages = db.experiments.find(page=table.active_page, **fnc_context)
    context.update({
        "experiments": experiments,
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
    
    experiments, num_pages = db.experiments.find(page=page, **fnc_context)

    context.update({
        "experiments": experiments,
        "template_name_or_list": "components/search/experiment.html",
        "num_pages": num_pages,
    })
    return context