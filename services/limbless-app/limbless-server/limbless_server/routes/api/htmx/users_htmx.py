from typing import TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, UserRole
from .... import db, logger

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

users_htmx = Blueprint("users_htmx", __name__, url_prefix="/api/hmtx/users/")


@users_htmx.route("get", methods=["GET"], defaults={"page": 0})
@users_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if sort_by not in models.User.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)

    with DBSession(db) as session:
        users, n_pages = session.get_users(offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending)
        
        return make_response(
            render_template(
                "components/tables/user.html", users=users,
                active_page=page, n_pages=n_pages,
                sort_by=sort_by, sort_order=sort_order
            )
        )


@users_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.form.keys()))
    query = request.form.get(field_name)

    if query is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (raw_roles := request.args.get("roles", None)) is not None:
        logger.debug(raw_roles)
        raw_roles = raw_roles.split(",")
        with_roles = []
        for raw_role in raw_roles:
            try:
                role_id = int(raw_role)
            except ValueError:
                continue
            with_roles.append(UserRole.get(role_id))
    else:
        with_roles = None

    only_insiders = request.args.get("only_insiders") == "True"
    results = db.query_users(query, with_roles=with_roles, only_insiders=only_insiders)
    
    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results, field_name=field_name
        )
    )


@users_htmx.route("table_query/<string:field_name>", methods=["POST"])
@login_required
def table_query(field_name: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if field_name == "first_name" or field_name == "last_name":
        users = db.query_users(word)
    elif field_name == "email":
        users = db.query_users_by_email(word)
    elif field_name == "id":
        try:
            user_id = int(word)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        else:
            users = [db.get_user(user_id)]
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    return make_response(
        render_template(
            "components/tables/user.html",
            current_query=word,
            users=users,
            field_name=field_name
        )
    )


@users_htmx.route("<int:user_id>/get_projects", methods=["GET"], defaults={"page": 0})
@users_htmx.route("<int:user_id>/get_projects/<int:page>", methods=["GET"])
@login_required
def get_projects(user_id: int, page: int):
    import time
    time.sleep(1)
    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if user.id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT
    
    with DBSession(db) as session:
        projects, n_pages = session.get_projects(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending)
    
    return make_response(
        render_template(
            "components/tables/user-project.html",
            user=user, projects=projects,
            active_page=page, n_pages=n_pages
        )
    )


@users_htmx.route("<int:user_id>/query_projects/<string:field_name>", methods=["GET"])
@login_required
def query_projects(user_id: int, field_name: str):
    if (word := request.args.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if user.id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    projects = []
    if field_name == "name":
        projects = db.query_projects(word, user_id=user_id)
    elif field_name == "id":
        try:
            project_id = int(word)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        else:
            project = db.get_project(project_id)
            if project is not None and project.owner_id == user_id:
                projects.append(project)
    
    return make_response(
        render_template(
            "components/tables/user-project.html",
            user=user, projects=projects, field_name=field_name,
        )
    )


@users_htmx.route("<int:user_id>/get_seq_requests", methods=["GET"], defaults={"page": 0})
@users_htmx.route("<int:user_id>/get_seq_requests/<int:page>", methods=["GET"])
@login_required
def get_seq_requests(user_id: int, page: int):
    import time
    time.sleep(1)
    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if user.id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT
    
    with DBSession(db) as session:
        seq_requests, n_pages = session.get_seq_requests(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending)
    
    return make_response(
        render_template(
            "components/tables/user-seq_request.html",
            user=user, seq_requests=seq_requests,
            active_page=page, n_pages=n_pages
        )
    )


@users_htmx.route("<int:user_id>/query_seq_requests/<string:field_name>", methods=["GET"])
@login_required
def query_seq_requests(user_id: int, field_name: str):
    if (word := request.args.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if user.id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    seq_requests = []
    if field_name == "id":
        try:
            seq_request_id = int(word)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        else:
            seq_request = db.get_seq_request(seq_request_id)
            if seq_request is not None and seq_request.requestor_id == user_id:
                seq_requests.append(seq_request)
    
    return make_response(
        render_template(
            "components/tables/user-seq_request.html",
            user=user, seq_requests=seq_requests, field_name=field_name,
        )
    )