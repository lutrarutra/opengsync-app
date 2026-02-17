import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .. import forms
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context
from ..tools.spread_sheet_components import TextColumn
from ..tools import StaticSpreadSheet
from ..forms.HTMXFlaskForm import HTMXFlaskForm

class LibraryTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Pool", label="pool_name", col_size=1, search_type="text", sortable=True, sort_by="pool_id"),
        TableCol(title="Library Type", label="type", col_size=1, choices=cats.LibraryType.as_list()),
        TableCol(title="Status", label="status", col_size=1, sortable=True, sort_by="status_id", choices=cats.LibraryStatus.as_list()),
        TableCol(title="Request", label="seq_request", col_size=2),
        TableCol(title="Owner", label="owner", col_size=1),
    ]

def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = LibraryTable(route="libraries_htmx.get", page=request.args.get("page", 0, type=int))

    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [cats.LibraryStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (type_in := request.args.get("type_in")):
        type_in = json.loads(type_in)
        try:
            type_in = [cats.LibraryType.get(int(type_)) for type_ in type_in]
            if type_in:
                fnc_context["type_in"] = type_in
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")):
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (pool_name := request.args.get("pool_name")):
        fnc_context["pool_name"] = pool_name
        table.active_search_var = "pool_name"
        table.active_query_value = pool_name
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
        if sort_by not in models.Library.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending
    
    context = parse_context(current_user, request) | kwargs

    if (pool := context.get("pool")) is not None:
        template = "components/tables/pool-library.html"        
        fnc_context["pool_id"] = pool.id
        table.url_params["pool_id"] = pool.id
    elif (experiment := context.get("experiment")) is not None:      
        template = "components/tables/experiment-library.html"  
        fnc_context["experiment_id"] = experiment.id
        table.url_params["experiment_id"] = experiment.id
    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-library.html"
        fnc_context["lab_prep_id"] = lab_prep.id
        table.url_params["lab_prep_id"] = lab_prep.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-library.html"        
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id
    elif (sample := context.get("sample")) is not None:
        template = "components/tables/sample-library.html"        
        fnc_context["sample_id"] = sample.id
        table.url_params["sample_id"] = sample.id
    else:
        template = "components/tables/library.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id

    libraries, table.num_pages = db.libraries.find(page=table.active_page, **fnc_context)
        
    context.update({
        "libraries": libraries,
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
    
    libraries, num_pages = db.libraries.find(page=page, **fnc_context)

    context.update({
        "libraries": libraries,
        "template_name_or_list": "components/search/library.html",
        "num_pages": num_pages,
    })
    return context


def get_properties_form(current_user: models.User, request: Request, **kwargs) -> HTMXFlaskForm:
    context = parse_context(current_user, request) | kwargs
    fnc_context = {}

    if (seq_request := context.get("seq_request")) is not None:
        fnc_context["seq_request_id"] = seq_request.id
    elif (project := context.get("project")) is not None:
        fnc_context["project_id"] = project.id
    else:
        raise exceptions.BadRequestException("No sequence request context provided.")
    
    form = forms.LibraryPropertyForm(
        editable=current_user.is_insider(),
        seq_request=context.get("seq_request"),
        project=context.get("project"),
        formdata=request.form if request.method == "POST" else None,
    )
    return form

