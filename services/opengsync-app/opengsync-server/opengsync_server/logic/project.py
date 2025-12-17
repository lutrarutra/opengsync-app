import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class ProjectTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=1, search_type="text", sortable=True),
        TableCol(title="Title", label="title", col_size=3, search_type="text", sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=2, choices=cats.LibraryType.as_list()),
        TableCol(title="Status", label="status", col_size=1, search_type="text", sort_by="status_id", sortable=True, choices=cats.ProjectStatus.as_list()),
        TableCol(title="Group", label="group", col_size=2),
        TableCol(title="Owner", label="owner_name", col_size=2, search_type="text"),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
    ]

def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = ProjectTable(route="projects_htmx.get", page=request.args.get("page", 0, type=int))

    if (identifier := request.args.get("identifier")):
        fnc_context["identifier"] = identifier
        table.active_search_var = "identifier"
        table.active_query_value = identifier
    elif (title := request.args.get("title")):
        fnc_context["title"] = title
        table.active_search_var = "title"
        table.active_query_value = title
    elif (project_id := request.args.get("id")):
        try:
            project_id = int(project_id)
            fnc_context["id"] = project_id
            table.active_search_var = "id"
            table.active_query_value = str(project_id)
        except ValueError:
            raise exceptions.BadRequestException()
    elif (owner_name := request.args.get("owner_name")):
        fnc_context["owner_name"] = owner_name
        table.active_search_var = "owner_name"
        table.active_query_value = owner_name
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.Project.sortable_fields:
            raise exceptions.BadRequestException()

        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending
    
    context = parse_context(current_user, request) | kwargs

    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [cats.ProjectStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
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
        template = "components/tables/user-project.html"
        fnc_context["user_id"] = user.id
        table.url_params["user_id"] = user.id

    elif (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-project.html"        
        fnc_context["experiment_id"] = experiment.id
        table.url_params["experiment_id"] = experiment.id

    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-project.html"
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id

    elif (group := context.get("group")) is not None:
        template = "components/tables/group-project.html"
        fnc_context["group_id"] = group.id
        table.url_params["group_id"] = group.id
    else:
        template = "components/tables/project.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id

    projects, table.num_pages = db.projects.find(page=table.active_page, **fnc_context)

    context.update({
        "projects": projects,
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
    
    if (identifier := request.args.get("identifier")) is not None:
        if (identifier := identifier.strip()):
            fnc_context["identifier"] = identifier
        else:
            fnc_context["sort_by"] = "identifier"
    elif (title := request.args.get("title")) is not None:
        if (title := title.strip()):
            fnc_context["title"] = title
        else:
            fnc_context["sort_by"] = "title"
    elif (project_id := request.args.get("id")) is not None:
        try:
            project_id = int(project_id)
            fnc_context["id"] = project_id
        except ValueError:
            raise exceptions.BadRequestException()
    elif (owner_name := request.args.get("owner_name")) is not None:
        if (owner_name := owner_name.strip()):
            fnc_context["owner_name"] = owner_name
        else:
            fnc_context["sort_by"] = "owner_name"
    elif (identifier_title := request.args.get("identifier_title")) is not None:
        if (identifier_title := identifier_title.strip()):
            fnc_context["identifier_title"] = identifier_title
        else:
            fnc_context["sort_by"] = "title"
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")

    if (group := context.get("group")) is not None:
        fnc_context["group_id"] = group.id
    else:
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id
    
    projects, num_pages = db.projects.find(page=page, **fnc_context)

    context.update({
        "projects": projects,
        "template_name_or_list": "components/search/project.html",
        "num_pages": num_pages,
    })
    return context