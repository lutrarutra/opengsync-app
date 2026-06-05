import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context


class SampleTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Project", label="project", col_size=2),
        TableCol(title="Status", label="status", col_size=2, sortable=True, sort_by="status_id", choices=C.SampleStatus.as_selectable()),
        TableCol(title="Owner", label="owner", col_size=1),
        TableCol(title="# Libraries", label="num_libraries", col_size=1),
        TableCol(title="Library Types", label="library_types", col_size=4),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = SampleTable(route="samples_htmx.get", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs
    stmt = sa.select(models.Sample)
    
    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.SampleStatus.get(int(status)) for status in status_in]
            if status_in:
                stmt = Q.sample.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")):
        stmt = Q.sample.select(search_name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.sample.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"

        try:
            stmt = stmt.order_by(getattr(getattr(models.Sample, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (library := context.get("library")) is not None:
        template = "components/tables/library-sample.html"        
        stmt = Q.sample.select(library_id=library.id, statement=stmt)
        table.url_params["library_id"] = library.id
    elif (project := context.get("project")) is not None:
        template = "components/tables/project-sample.html"        
        stmt = Q.sample.select(project_id=project.id, statement=stmt)
        table.url_params["project_id"] = project.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-sample.html"        
        stmt = Q.sample.select(seq_request_id=seq_request.id, statement=stmt)
        table.url_params["seq_request_id"] = seq_request.id
    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-sample.html"
        stmt = Q.sample.select(lab_prep_id=lab_prep.id, statement=stmt)
        table.url_params["lab_prep_id"] = lab_prep.id
    else:
        template = "components/tables/sample.html"
        if not current_user.is_insider():
            stmt = Q.sample.select(user_id=current_user.id, statement=stmt)

    # samples, table.num_pages = db.samples.find(page=table.active_page, **fnc_context)
    samples, count = db.session.page(stmt, page=table.active_page or 0)
    
    context.update({
        "samples": samples,
        "template_name_or_list": template,
        "table": table,
    })
    return context


def get_browse_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    table = SampleTable(route="samples_htmx.browse", page=request.args.get("page", 0, type=int))
    table.url_params["workflow"] = kwargs["workflow"]
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    context = parse_context(current_user, request) | kwargs
    stmt = sa.select(models.Sample)

    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.SampleStatus.get(int(status)) for status in status_in]
            if status_in:
                stmt = Q.sample.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")):
        stmt = Q.sample.select(search_name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.sample.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.Sample, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (seq_request := context.get("seq_request")) is not None:
        stmt = Q.sample.select(seq_request_id=seq_request.id, statement=stmt)
    if (pool := context.get("pool")) is not None:
        stmt = Q.sample.select(pool_id=pool.id, statement=stmt)

    # samples, table.num_pages = db.samples.find(page=table.active_page, **fnc_context)
    samples, count = db.session.page(stmt, page=table.active_page or 0)

    context.update({
        "samples": samples,
        "template_name_or_list": "components/tables/select-samples.html",
        "table": table,
    })
    return context