import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class ProjectTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=1, searchable=True, sortable=True),
        TableCol(title="Title", label="title", col_size=3, searchable=True, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=2, choices=C.LibraryType.as_selectable()),
        TableCol(title="Status", label="status", col_size=1, sort_by="status_id", sortable=True, choices=C.ProjectStatus.as_selectable()),
        TableCol(title="Group", label="group", col_size=2),
        TableCol(title="Owner", label="owner_name", col_size=2, searchable=True),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
    ]

def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = ProjectTable(route="render_project_table", page=request.args.get("page", 0, type=int))

    stmt = sa.select(models.Project)

    if (identifier := request.args.get("identifier")):
        stmt = Q.project.select(search_identifier=identifier, statement=stmt)
        table.active_search_var = "identifier"
        table.active_query_value = identifier
    elif (title := request.args.get("title")):
        stmt = Q.project.select(search_title=title, statement=stmt)
        table.active_search_var = "title"
        table.active_query_value = title
    elif (project_id := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(project_id)
        try:
            project_id = int("".join(filter(str.isdigit, project_id)))
            stmt = Q.project.select(id=project_id, statement=stmt)
        except ValueError:
            pass
    elif (owner_name := request.args.get("owner_name")):
        stmt = Q.project.select(search_owner_name=owner_name, statement=stmt)
        table.active_search_var = "owner_name"
        table.active_query_value = owner_name
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"

        try:
            stmt = stmt.order_by(getattr(getattr(models.Project, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()

        table.active_sort_var = sort_by
        table.active_sort_descending = descending
    
    context = parse_context(current_user, request) | kwargs

    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.ProjectStatus.get(int(status)) for status in status_in]
            if status_in:
                stmt = Q.project.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (library_types_in := request.args.get("library_types_in")):
        library_types_in = json.loads(library_types_in)
        try:
            library_types_in = [C.LibraryType.get(int(library_type)) for library_type in library_types_in]
            if library_types_in:
                stmt = Q.project.select(library_types_in=library_types_in, statement=stmt)
                table.filter_values["library_types"] = library_types_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (user := context.get("user")) is not None:
        template = "components/tables/user-project.html"
        stmt = Q.project.select(user_id=user.id, statement=stmt)
        table.url_params["user_id"] = user.id
    elif (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-project.html"        
        stmt = Q.project.select(experiment_id=experiment.id, statement=stmt)
        table.url_params["experiment_id"] = experiment.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-project.html"
        stmt = Q.project.select(seq_request_id=seq_request.id, statement=stmt)
        table.url_params["seq_request_id"] = seq_request.id
    elif (group := context.get("group")) is not None:
        template = "components/tables/group-project.html"
        stmt = Q.project.select(group_id=group.id, statement=stmt)
        table.url_params["group_id"] = group.id
    else:
        template = "components/tables/project.html"
        if not current_user.is_insider():
            stmt = Q.project.select(user_id=current_user.id, statement=stmt)

    projects, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)

    context.update({
        "projects": projects,
        "template_name_or_list": template,
        "table": table,
    })
    return context

def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    context = parse_context(current_user, request) | kwargs
    page = request.args.get("page", 0, type=int)

    stmt = sa.select(models.Project)
    
    if (identifier := request.args.get("identifier")) is not None:
        if (identifier := identifier.strip()):
            stmt = Q.project.select(search_identifier=identifier, statement=stmt)
        else:
            stmt = stmt.order_by(sa.nulls_last(models.Project.identifier.asc()))
    elif (title := request.args.get("title")) is not None:
        if (title := title.strip()):
            stmt = Q.project.select(search_title=title, statement=stmt)
        else:
            stmt = stmt.order_by(sa.nulls_last(models.Project.title.asc()))
    elif (owner_name := request.args.get("owner_name")) is not None:
        if (owner_name := owner_name.strip()):
            stmt = Q.project.select(search_owner_name=owner_name, statement=stmt)
        else:
            stmt = stmt.join(models.User, models.User.id == models.Project.owner_id).order_by(sa.nulls_last(models.User.name.asc()))
    elif (identifier_title := request.args.get("identifier_title")) is not None:
        if (identifier_title := identifier_title.strip()):
            stmt = Q.project.select(search_identifier_title=identifier_title, statement=stmt)
        else:
            stmt = stmt.order_by(sa.nulls_last(models.Project.title.asc()), sa.nulls_last(models.Project.identifier.asc()))
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")

    if (group := context.get("group")) is not None:
        stmt = Q.project.select(group_id=group.id, statement=stmt)
    else:
        if not current_user.is_insider():
            stmt = Q.project.select(user_id=current_user.id, statement=stmt)
    
    projects, _ = db.session.page(stmt, page=page)

    context.update({
        "projects": projects,
        "template_name_or_list": "components/search/project.html",
    })
    return context