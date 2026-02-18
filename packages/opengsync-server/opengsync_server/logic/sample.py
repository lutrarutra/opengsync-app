import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context


class SampleTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Project", label="project", col_size=2),
        TableCol(title="Status", label="status", col_size=2, sortable=True, sort_by="status_id", choices=cats.SampleStatus.as_list()),
        TableCol(title="Owner", label="owner", col_size=1),
        TableCol(title="# Libraries", label="num_libraries", col_size=1),
        TableCol(title="Library Types", label="library_types", col_size=4),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = SampleTable(route="samples_htmx.get", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs
    
    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [cats.SampleStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
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
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.Sample.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (library := context.get("library")) is not None:
        template = "components/tables/library-sample.html"        
        fnc_context["library_id"] = library.id
        table.url_params["library_id"] = library.id
    elif (project := context.get("project")) is not None:
        template = "components/tables/project-sample.html"        
        fnc_context["project_id"] = project.id
        table.url_params["project_id"] = project.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-sample.html"        
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id
    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-sample.html"
        fnc_context["lab_prep_id"] = lab_prep.id
        table.url_params["lab_prep_id"] = lab_prep.id
    else:
        template = "components/tables/sample.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id

    samples, table.num_pages = db.samples.find(page=table.active_page, **fnc_context)
    
    context.update({
        "samples": samples,
        "template_name_or_list": template,
        "table": table,
    })
    return context