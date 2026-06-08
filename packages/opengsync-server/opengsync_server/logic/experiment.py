import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class ExperimentTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=2, searchable=True, sortable=True),
        TableCol(title="Workflow", label="workflow", col_size=2, choices=C.ExperimentWorkFlow.as_selectable(), sortable=True, sort_by="workflow_id"),
        TableCol(title="Status", label="status", col_size=2, choices=C.ExperimentStatus.as_selectable(), sortable=True, sort_by="status_id"),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=3, choices=C.LibraryType.as_selectable()),
        TableCol(title="Operator", label="operator", col_size=2, searchable=True),
        TableCol(title="Created", label="timestamp_created", col_size=2, sortable=True, sort_by="timestamp_created_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:    
    table = ExperimentTable(route="experiments_htmx.get", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs

    stmt = sa.select(models.Experiment)

    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.ExperimentStatus.get(int(status)) for status in status_in]
            if status_in:
                stmt = Q.experiment.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()  
    
    if (workflow_in := request.args.get("workflow_in")):
        workflow_in = json.loads(workflow_in)
        try:
            workflow_in = [C.ExperimentWorkFlow.get(int(workflow)) for workflow in workflow_in]
            if workflow_in:
                stmt = Q.experiment.select(workflow_in=workflow_in, statement=stmt)
                table.filter_values["workflow"] = workflow_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")):
        stmt = Q.experiment.select(search_name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (operator := request.args.get("operator")):
        stmt = Q.experiment.select(search_operator_name=operator, statement=stmt)
        table.active_search_var = "operator"
        table.active_query_value = operator
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.experiment.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.Experiment.sortable_fields:
            raise exceptions.BadRequestException()
        
        try:
            stmt = stmt.order_by(getattr(getattr(models.Experiment, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (project := context.get("project")) is not None:
        template = "components/tables/project-experiment.html"        
        stmt = Q.experiment.select(project_id=project.id, statement=stmt)
        table.url_params["project_id"] = project.id
    else:
        if not current_user.is_insider():
            raise exceptions.NoPermissionsException("You do not have permission to view this resource.")
        template = "components/tables/experiment.html"

    experiments, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)
    context.update({
        "experiments": experiments,
        "template_name_or_list": template,
        "table": table,
    })
    return context

def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.BadRequestException("You do not have permission to view this resource.")
    
    context = parse_context(current_user, request) | kwargs
    page = request.args.get("page", 0, type=int)

    stmt = sa.select(models.Experiment)
    
    if (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            stmt = Q.experiment.select(search_name=name, statement=stmt)
        else:
            stmt = stmt.order_by(sa.nulls_last(models.Experiment.name.asc()))
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")
    
    experiments, num_pages = db.session.page(stmt, page=page)

    context.update({
        "experiments": experiments,
        "template_name_or_list": "components/search/experiment.html",
        "num_pages": num_pages,
    })
    return context


def get_browse_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    table = ExperimentTable(route="experiments_htmx.browse", page=request.args.get("page", 0, type=int))
    table.url_params["workflow"] = kwargs["workflow"]
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    context = parse_context(current_user, request) | kwargs

    stmt = sa.select(models.Experiment)

    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.ExperimentStatus.get(int(status)) for status in status_in]
            if status_in:
                stmt = Q.experiment.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()  
    
    if (workflow_in := request.args.get("workflow_in")):
        workflow_in = json.loads(workflow_in)
        try:
            workflow_in = [C.ExperimentWorkFlow.get(int(workflow)) for workflow in workflow_in]
            if workflow_in:
                stmt = Q.experiment.select(workflow_in=workflow_in, statement=stmt)
                table.filter_values["workflow"] = workflow_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.experiment.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    elif (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            stmt = Q.experiment.select(search_name=name, statement=stmt)
        else:
            stmt = stmt.order_by(sa.nulls_last(models.Experiment.name.asc()))
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"

        try:
            stmt = stmt.order_by(getattr(getattr(models.Experiment, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()

        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    experiments, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)

    context.update({
        "experiments": experiments,
        "template_name_or_list": "components/tables/select-experiments.html",
        "table": table,
    })
    return context