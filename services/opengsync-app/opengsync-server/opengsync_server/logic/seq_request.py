import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class SeqRequestTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=4, search_type="text", sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=3, choices=cats.LibraryType.as_list()),
        TableCol(title="Status", label="status", col_size=1, sortable=True, sort_by="status_id", choices=cats.SeqRequestStatus.as_list()),
        TableCol(title="Submission Type", label="submission_type", col_size=1, choices=cats.SubmissionType.as_list()),
        TableCol(title="Group", label="group", col_size=2, search_type="text"),
        TableCol(title="Requestor", label="requestor", col_size=2, search_type="text"),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
        TableCol(title="Submitted", label="timestamp_submitted", col_size=2, sortable=True, sort_by="timestamp_submitted_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}

    table = SeqRequestTable(route="seq_requests_htmx.get", page=request.args.get("page", 0, type=int))
    
    context = parse_context(current_user, request) | kwargs
    
    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [cats.SeqRequestStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (submission_type_in := request.args.get("submission_type_in")):
        submission_type_in = json.loads(submission_type_in)
        try:
            submission_type_in = [cats.SubmissionType.get(int(submission_type)) for submission_type in submission_type_in]
            if submission_type_in:
                fnc_context["submission_type_in"] = submission_type_in
                table.filter_values["submission_type"] = submission_type_in
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

    if (user := context.get("user")) is not None:
        template = "components/tables/user-seq_request.html"
        fnc_context["user_id"] = user.id
        table.url_params["user_id"] = user.id
    elif (group := context.get("group")) is not None:
        template = "components/tables/group-seq_request.html"
        fnc_context["group_id"] = group.id
        table.url_params["group_id"] = group.id
    elif (project := context.get("project")) is not None:
        template = "components/tables/project-seq_request.html"        
        fnc_context["project_id"] = project.id
        table.url_params["project_id"] = project.id
    else:
        template = "components/tables/seq_request.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id

    if (name := request.args.get("name")):
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (requestor_name := request.args.get("requestor")):
        fnc_context["requestor_name"] = requestor_name
        table.active_search_var = "requestor"
        table.active_query_value = requestor_name
    elif (group := request.args.get("group")):
        fnc_context["group"] = group
        table.active_search_var = "group"
        table.active_query_value = group
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
        if sort_by not in models.SeqRequest.sortable_fields:
            raise exceptions.BadRequestException(f"SeqRequest table cannot be sorted by '{sort_by}'.")

        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    seq_requests, table.num_pages = db.seq_requests.find(page=table.active_page, **fnc_context)

    context.update({
        "seq_requests": seq_requests,
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

    if (user := context.get("user")) is not None:
        fnc_context["user_id"] = user.id
    elif (group := context.get("group")) is not None:
        fnc_context["group_id"] = group.id
    elif (project := context.get("project")) is not None:
        fnc_context["project_id"] = project.id
    else:
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id
    
    logger.debug(fnc_context)
    seq_requests, num_pages = db.seq_requests.find(page=page, **fnc_context)
    
    context.update({
        "seq_requests": seq_requests,
        "template_name_or_list": "components/search/seq_request.html",
        "num_pages": num_pages,
    })
    return context