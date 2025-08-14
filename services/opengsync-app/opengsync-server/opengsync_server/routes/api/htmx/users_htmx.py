import json

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import HTTPResponse, UserRole, SeqRequestStatus
from .... import db, logger  # noqa F401
from ....core import wrappers

users_htmx = Blueprint("users_htmx", __name__, url_prefix="/api/hmtx/users/")


@wrappers.htmx_route(users_htmx, db=db)
def get(current_user: models.User, page: int = 0):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if sort_by not in models.User.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (role_in := request.args.get("role_id_in")) is not None:
        role_in = json.loads(role_in)
        try:
            role_in = [UserRole.get(int(role)) for role in role_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(role_in) == 0:
            role_in = None

    users, n_pages = db.get_users(
        offset=PAGE_LIMIT * page, sort_by=sort_by, descending=descending,
        role_in=role_in, count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/user.html", users=users,
            active_page=page, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order,
            UserRole=UserRole, role_in=role_in
        )
    )


@wrappers.htmx_route(users_htmx, db=db, methods=["POST"])
def query():
    field_name = next(iter(request.form.keys()))
    query = request.form.get(field_name)

    if query is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (role_in := request.args.get("role_id_in")) is not None:
        role_in = json.loads(role_in)
        try:
            role_in = [UserRole.get(int(role)) for role in role_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if len(role_in) == 0:
            role_in = None

    only_insiders = request.args.get("only_insiders") == "True"
    results = db.query_users(query, role_in=role_in, only_insiders=only_insiders)
    
    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results, field_name=field_name
        )
    )


@wrappers.htmx_route(users_htmx, db=db)
def table_query():
    if (word := request.args.get("last_name")) is not None:
        field_name = "last_name"
    elif (word := request.args.get("email")) is not None:
        field_name = "email"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if (role_in := request.args.get("role_id_in")) is not None:
        role_in = json.loads(role_in)
        try:
            role_in = [UserRole.get(int(role)) for role in role_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if len(role_in) == 0:
            role_in = None

    users: list[models.User] = []
    if field_name == "last_name":
        users = db.query_users(word, role_in=role_in)
    elif field_name == "email":
        users = db.query_users_by_email(word, role_in=role_in)
    elif field_name == "id":
        try:
            _id = int(word)
            if (user := db.get_user(_id)) is not None:
                users.append(user)
        except ValueError:
            pass

    return make_response(
        render_template(
            "components/tables/user.html",
            current_query=word, active_query_field=field_name,
            users=users, role_in=role_in
        )
    )


@wrappers.htmx_route(users_htmx, db=db)
def get_projects(current_user: models.User, user_id: int, page: int = 0):
    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if user.id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT
    
    projects, n_pages = db.get_projects(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, count_pages=True)
    
    return make_response(
        render_template(
            "components/tables/user-project.html",
            user=user, projects=projects,
            active_page=page, n_pages=n_pages
        )
    )


@wrappers.htmx_route(users_htmx, db=db)
def get_seq_requests(current_user: models.User, user_id: int, page: int = 0):
    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if user.id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SeqRequestStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
    
    seq_requests, n_pages = db.get_seq_requests(
        offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, status_in=status_in, count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/user-seq_request.html",
            user=user, seq_requests=seq_requests,
            active_page=page, n_pages=n_pages
        )
    )


@wrappers.htmx_route(users_htmx, db=db)
def query_seq_requests(current_user: models.User, user_id: int):
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if user.id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SeqRequestStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    seq_requests: list[models.SeqRequest] = []
    if field_name == "name":
        seq_requests = db.query_seq_requests(word, user_id=user_id, status_in=status_in)
    elif field_name == "id":
        try:
            _id = int(word)
            if (seq_request := db.get_seq_request(_id)) is not None:
                if seq_request.requestor_id == user_id:
                    seq_requests.append(seq_request)
        except ValueError:
            pass

    return make_response(
        render_template(
            "components/tables/user-seq_request.html",
            current_query=word, active_query_field=field_name,
            seq_requests=seq_requests, status_in=status_in,
            user=user
        )
    )


@wrappers.htmx_route(users_htmx, db=db)
def get_affiliations(current_user: models.User, user_id: int, page: int = 0):
    if (user := db.get_user(user_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if user.id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "group_id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    affiliations, n_pages = db.get_user_affiliations(
        offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/user-affiliation.html",
            user=user, affiliations=affiliations,
            active_page=page, n_pages=n_pages
        )
    )