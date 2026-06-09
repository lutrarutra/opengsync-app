import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class LabPrepTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=2, searchable=True, sortable=True),
        TableCol(title="Checklist", label="checklist", col_size=2, choices=C.LabChecklistType.as_selectable(), sortable=True, sort_by="checklist_type_id"),
        TableCol(title="Service", label="service", col_size=2, choices=C.ServiceType.as_selectable(), sortable=True, sort_by="service_type_id"),
        TableCol(title="Status", label="status", col_size=2, choices=C.PrepStatus.as_selectable(), sortable=True, sort_by="status_id"),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
        TableCol(title="Creator", label="creator", col_size=2, searchable=True),
        TableCol(title="Library Types", label="library_types", col_size=2),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permission to view this resource.")
    
    table = LabPrepTable(route="lab_preps_htmx.get", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs

    stmt = sa.select(models.LabPrep)
    
    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.PrepStatus.get(int(status)) for status in status_in]
            if status_in:
                stmt = Q.lab_prep.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (checklist_type_in := request.args.get("checklist_in")):
        checklist_type_in = json.loads(checklist_type_in)
        try:
            checklist_type_in = [C.LabChecklistType.get(int(checklist_type)) for checklist_type in checklist_type_in]
            if checklist_type_in:
                stmt = Q.lab_prep.select(checklist_type_in=checklist_type_in, statement=stmt)
                table.filter_values["checklist"] = checklist_type_in
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (service_in := request.args.get("service_in")):
        service_in = json.loads(service_in)
        try:
            service_in = [C.ServiceType.get(int(service)) for service in service_in]
            if service_in:
                stmt = Q.lab_prep.select(service_type_in=service_in, statement=stmt)
                table.filter_values["service"] = service_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")):
        stmt = Q.lab_prep.select(search_name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            id_ = int("".join(filter(str.isdigit, id_)))
            stmt = Q.lab_prep.select(id=id_, statement=stmt)
        except ValueError:
            pass
    elif (creator := request.args.get("creator")):
        stmt = Q.lab_prep.select(search_creator_name=creator, statement=stmt)
        table.active_search_var = "creator"
        table.active_query_value = creator
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.LabPrep, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    template = "components/tables/lab_prep.html"

    lab_preps, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)
        
    context.update({
        "lab_preps": lab_preps,
        "template_name_or_list": template,
        "table": table,
    })
    return context