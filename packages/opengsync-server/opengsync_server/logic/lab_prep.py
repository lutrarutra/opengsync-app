import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class LabPrepTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=2, search_type="text", sortable=True),
        TableCol(title="Checklist", label="checklist", col_size=2, choices=cats.LabChecklistType.as_list(), sortable=True, sort_by="checklist_type_id"),
        TableCol(title="Service", label="service", col_size=2, choices=cats.ServiceType.as_list(), sortable=True, sort_by="service_type_id"),
        TableCol(title="Status", label="status", col_size=2, choices=cats.PrepStatus.as_list(), sortable=True, sort_by="status_id"),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
        TableCol(title="Creator", label="creator", col_size=2, search_type="text"),
        TableCol(title="Library Types", label="library_types", col_size=2),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permission to view this resource.")
    
    fnc_context = {}
    table = LabPrepTable(route="lab_preps_htmx.get", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs
    
    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [cats.PrepStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (checklist_type_in := request.args.get("checklist_in")):
        checklist_type_in = json.loads(checklist_type_in)
        try:
            checklist_type_in = [cats.LabChecklistType.get(int(checklist_type)) for checklist_type in checklist_type_in]
            if checklist_type_in:
                fnc_context["checklist_type_in"] = checklist_type_in
                table.filter_values["checklist"] = checklist_type_in
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (service_in := request.args.get("service_in")):
        service_in = json.loads(service_in)
        try:
            service_in = [cats.ServiceType.get(int(service)) for service in service_in]
            if service_in:
                fnc_context["service_in"] = service_in
                table.filter_values["service"] = service_in
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
    elif (creator := request.args.get("creator")):
        fnc_context["creator"] = creator
        table.active_search_var = "creator"
        table.active_query_value = creator
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.LabPrep.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-lab_prep.html"        
        fnc_context["experiment_id"] = experiment.id
        table.url_params["experiment_id"] = experiment.id
    else:
        template = "components/tables/lab_prep.html"

    lab_preps, table.num_pages = db.lab_preps.find(page=table.active_page, **fnc_context)
        
    context.update({
        "lab_preps": lab_preps,
        "template_name_or_list": template,
        "table": table,
    })
    return context