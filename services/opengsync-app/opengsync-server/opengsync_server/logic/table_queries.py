import json

from flask import Request

from opengsync_db import models, categories, PAGE_LIMIT

from ..import db
from ..core import exceptions
from .context import parse_context

def query_projects_table(current_user: models.User, request: Request, **kwargs) -> dict:
    context = {}

    page = request.args.get("page", 0, type=int)
    offset = page * PAGE_LIMIT

    query_fnc = None

    if (identifier := request.args.get("identifier", None)) is not None:
        field_name = "identifier"
        query_fnc = lambda word, **kwargs: db.projects.query(identifier=word, **kwargs)
    elif (title := request.args.get("title", None)) is not None:
        field_name = "title"
        query_fnc = lambda word, **kwargs: db.projects.query(title=word, **kwargs)
    elif (id := request.args.get("id", None)) is not None:
        field_name = "id"
        query_fnc = lambda id, **kwargs: db.projects.query(id=id, **kwargs)
        try:
            id = int(id)
        except ValueError:
            raise exceptions.BadRequestException()
    elif (owner_name := request.args.get("owner_id", None)) is not None:
        field_name = "owner_id"
    else:
        raise exceptions.BadRequestException()
    
    context |= parse_context(current_user, request) | kwargs

    if (user := context.get("user")) is not None:
        template = "components/tables/user-project.html"
        projects, n_pages = db.projects.query()
        context["user"] = user

    elif (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-project.html"        
        projects, n_pages = db.projects.find(offset=offset, experiment_id=experiment.id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["experiment"] = experiment

    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-project.html"
        projects, n_pages = db.projects.find(offset=offset, seq_request_id=seq_request.id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["seq_request"] = seq_request

    elif (group := context.get("group")) is not None:
        template = "components/tables/group-project.html"
        projects, n_pages = db.projects.find(offset=offset, group_id=group.id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["group"] = group
    else:
        template = "components/tables/project.html"
        if not current_user.is_insider():
            user_id = current_user.id
        else:
            user_id = None
        projects, n_pages = db.projects.find(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)

    context.update({
        "projects": projects,
        "n_pages": n_pages,
        "active_page": page,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "status_in": status_in,
        "template_name_or_list": template,
    })

    return context