import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class SeqRequestTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=4, searchable=True, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=3, choices=C.LibraryType.as_selectable()),
        TableCol(title="Status", label="status", col_size=1, sortable=True, sort_by="status_id", choices=C.SeqRequestStatus.as_selectable()),
        TableCol(title="Submission Type", label="submission_type", col_size=1, choices=C.SubmissionType.as_selectable()),
        TableCol(title="Group", label="group", col_size=2, searchable=True),
        TableCol(title="Requestor", label="requestor", col_size=2, searchable=True),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
        TableCol(title="Submitted", label="timestamp_submitted", col_size=2, sortable=True, sort_by="timestamp_submitted_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = SeqRequestTable(route="render_seq_request_table", page=request.args.get("page", 0, type=int))

    stmt = sa.select(models.SeqRequest)
    
    context = parse_context(current_user, request) | kwargs
    
    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.SeqRequestStatus.get(int(status)) for status in status_in]
            if status_in:
                stmt = Q.seq_request.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (submission_type_in := request.args.get("submission_type_in")):
        submission_type_in = json.loads(submission_type_in)
        try:
            submission_type_in = [C.SubmissionType.get(int(submission_type)) for submission_type in submission_type_in]
            if submission_type_in:
                stmt = Q.seq_request.select(submission_type_in=submission_type_in, statement=stmt)
                table.filter_values["submission_type"] = submission_type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (library_types_in := request.args.get("library_types_in")):
        library_types_in = json.loads(library_types_in)
        try:
            library_types_in = [C.LibraryType.get(int(library_type)) for library_type in library_types_in]
            if library_types_in:
                stmt = Q.seq_request.select(library_types_in=library_types_in, statement=stmt)
                table.filter_values["library_types"] = library_types_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (user := context.get("user")) is not None:
        template = "components/tables/user-seq_request.html"
        stmt = Q.seq_request.select(requestor_id=user.id, statement=stmt)
        table.url_params["user_id"] = user.id
    elif (group := context.get("group")) is not None:
        template = "components/tables/group-seq_request.html"
        stmt = Q.seq_request.select(group_id=group.id, statement=stmt)
        table.url_params["group_id"] = group.id
    elif (project := context.get("project")) is not None:
        template = "components/tables/project-seq_request.html"        
        stmt = Q.seq_request.select(project_id=project.id, statement=stmt)
        table.url_params["project_id"] = project.id
    else:
        template = "components/tables/seq_request.html"
        if not current_user.is_insider():
            stmt = Q.seq_request.select(requestor_id=current_user.id, statement=stmt)

    if (name := request.args.get("name")):
        stmt = Q.seq_request.select(search_name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (requestor_name := request.args.get("requestor")):
        stmt = Q.seq_request.select(search_requestor_name=requestor_name, statement=stmt)
        table.active_search_var = "requestor"
        table.active_query_value = requestor_name
    elif (group := request.args.get("group")):
        stmt = Q.seq_request.select(search_group_name=group, statement=stmt)
        table.active_search_var = "group"
        table.active_query_value = group
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.seq_request.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"

        try:
            stmt = stmt.order_by(getattr(getattr(models.SeqRequest, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    seq_requests, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)

    context.update({
        "seq_requests": seq_requests,
        "template_name_or_list": template,
        "table": table,
    })

    return context


def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    context = parse_context(current_user, request) | kwargs
    page = request.args.get("page", 0, type=int)

    stmt = sa.select(models.SeqRequest)
    
    if (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            stmt = Q.seq_request.select(search_name=name, statement=stmt)
        else:
            stmt = stmt.order_by(sa.nulls_last(models.SeqRequest.name.asc()))
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")

    if (user := context.get("user")) is not None:
        stmt = Q.seq_request.select(requestor_id=user.id, statement=stmt)
    elif (group := context.get("group")) is not None:
        stmt = Q.seq_request.select(group_id=group.id, statement=stmt)
    elif (project := context.get("project")) is not None:
        stmt = Q.seq_request.select(project_id=project.id, statement=stmt)
    else:
        if not current_user.is_insider():
            stmt = Q.seq_request.select(requestor_id=current_user.id, statement=stmt)
    
    seq_requests, count = db.session.page(stmt, page=page)
    
    context.update({
        "seq_requests": seq_requests,
        "template_name_or_list": "components/search/seq_request.html",
    })
    return context