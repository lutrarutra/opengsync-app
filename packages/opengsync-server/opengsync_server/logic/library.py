import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db
from .. import forms
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context
from ..forms.HTMXFlaskForm import HTMXFlaskForm

class LibraryTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Pool", label="pool_name", col_size=1, searchable=True, sortable=True, sort_by="pool_id"),
        TableCol(title="Library Type", label="type", col_size=1, choices=C.LibraryType.as_selectable()),
        TableCol(title="Status", label="status", col_size=1, sortable=True, sort_by="status_id", choices=C.LibraryStatus.as_selectable()),
        TableCol(title="Request", label="seq_request", col_size=2),
        TableCol(title="Owner", label="owner", col_size=1),
    ]

def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = LibraryTable(route="libraries_htmx.get", page=request.args.get("page", 0, type=int))
    stmt = sa.select(models.Library)

    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.LibraryStatus.get(int(status)) for status in status_in]
            if status_in:
                # fnc_context["status_in"] = status_in
                stmt = Q.library.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (type_in := request.args.get("type_in")):
        type_in = json.loads(type_in)
        try:
            type_in = [C.LibraryType.get(int(type_)) for type_ in type_in]
            if type_in:
                # fnc_context["type_in"] = type_in
                stmt = Q.library.select(type_in=type_in, statement=stmt)
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")):
        # fnc_context["name"] = name
        stmt = Q.library.search(name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (pool_name := request.args.get("pool_name")):
        # fnc_context["pool_name"] = pool_name
        stmt = Q.library.search(pool_name=pool_name, statement=stmt)
        table.active_search_var = "pool_name"
        table.active_query_value = pool_name
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.library.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        
        try:
            stmt = stmt.order_by(getattr(getattr(models.Library, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        
        table.active_sort_var = sort_by
        table.active_sort_descending = descending
    
    context = parse_context(current_user, request) | kwargs

    if (pool := context.get("pool")) is not None:
        template = "components/tables/pool-library.html"        
        stmt = Q.library.select(pool_id=pool.id, statement=stmt)
        table.url_params["pool_id"] = pool.id
    elif (experiment := context.get("experiment")) is not None:      
        template = "components/tables/experiment-library.html"  
        stmt = Q.library.select(experiment_id=experiment.id, statement=stmt)
        table.url_params["experiment_id"] = experiment.id
    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-library.html"
        stmt = Q.library.select(lab_prep_id=lab_prep.id, statement=stmt)
        table.url_params["lab_prep_id"] = lab_prep.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-library.html"        
        stmt = Q.library.select(seq_request_id=seq_request.id, statement=stmt)
        table.url_params["seq_request_id"] = seq_request.id
    elif (sample := context.get("sample")) is not None:
        template = "components/tables/sample-library.html"        
        stmt = Q.library.select(sample_id=sample.id, statement=stmt)
        table.url_params["sample_id"] = sample.id
    else:
        template = "components/tables/library.html"
        if not current_user.is_insider():
            stmt = Q.library.select(user_id=current_user.id, statement=stmt)

    libraries, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)
        
    context.update({
        "libraries": libraries,
        "template_name_or_list": template,
        "table": table,
    })

    return context


def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    context = parse_context(current_user, request) | kwargs
    page = request.args.get("page", 0, type=int)
    stmt = sa.select(models.Library)
    
    if (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            stmt = Q.library.search(name=name, statement=stmt)
        else:
            stmt = stmt.order_by(sa.nulls_last(models.Library.name.asc()))
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")

    if (pool := context.get("pool")) is not None:
        stmt = Q.library.select(pool_id=pool.id, statement=stmt)
    elif (experiment := context.get("experiment")) is not None:      
        stmt = Q.library.select(experiment_id=experiment.id, statement=stmt)
    elif (lab_prep := context.get("lab_prep")) is not None:
        stmt = Q.library.select(lab_prep_id=lab_prep.id, statement=stmt)
    elif (seq_request := context.get("seq_request")) is not None:
        stmt = Q.library.select(seq_request_id=seq_request.id, statement=stmt)
    elif (sample := context.get("sample")) is not None:
        stmt = Q.library.select(sample_id=sample.id, statement=stmt)
    else:
        if not current_user.is_insider():
            stmt = Q.library.select(user_id=current_user.id, statement=stmt)
    
    libraries, num_pages = db.session.page(stmt, page=page)

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

def get_browse_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    table = LibraryTable(route="libraries_htmx.browse", page=request.args.get("page", 0, type=int))
    table.url_params["workflow"] = kwargs["workflow"]
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    context = parse_context(current_user, request) | kwargs
    stmt = sa.select(models.Library)

    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.LibraryStatus.get(int(status)) for status in status_in]
            if status_in:
                stmt = Q.library.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (type_in := request.args.get("type_in")):
        type_in = json.loads(type_in)
        try:
            type_in = [C.LibraryType.get(int(type_)) for type_ in type_in]
            if type_in:
                stmt = Q.library.select(type_in=type_in, statement=stmt)
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")):
        stmt = Q.library.search(name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (pool_name := request.args.get("pool_name")):
        stmt = Q.library.search(pool_name=pool_name, statement=stmt)
        table.active_search_var = "pool_name"
        table.active_query_value = pool_name
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.library.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.Library, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (pool := context.get("pool")) is not None:
        stmt = Q.library.select(pool_id=pool.id, statement=stmt)
    elif (experiment := context.get("experiment")) is not None:      
        stmt = Q.library.select(experiment_id=experiment.id, statement=stmt)
    elif (lab_prep := context.get("lab_prep")) is not None:
        stmt = Q.library.select(lab_prep_id=lab_prep.id, statement=stmt)
    elif (seq_request := context.get("seq_request")) is not None:
        stmt = Q.library.select(seq_request_id=seq_request.id, statement=stmt)
    elif (sample := context.get("sample")) is not None:
        stmt = Q.library.select(sample_id=sample.id, statement=stmt)
    else:
        if not current_user.is_insider():
            stmt = Q.library.select(user_id=current_user.id, statement=stmt)

    libraries, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)
    context.update({
        "libraries": libraries,
        "template_name_or_list": "components/tables/select-libraries.html",
        "table": table,
    })
    return context