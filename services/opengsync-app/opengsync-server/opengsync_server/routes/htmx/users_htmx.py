import json

from flask import Blueprint, render_template, request
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import UserRole, SeqRequestStatus, ProjectStatus

from ... import db, logger, forms  # noqa F401
from ...core import wrappers, exceptions

users_htmx = Blueprint("users_htmx", __name__, url_prefix="/htmx/users/")


@wrappers.htmx_route(users_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get(current_user: models.User, page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if sort_by not in models.User.sortable_fields:
        raise exceptions.BadRequestException()
    
    if (role_in := request.args.get("role_id_in")) is not None:
        role_in = json.loads(role_in)
        try:
            role_in = [UserRole.get(int(role)) for role in role_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(role_in) == 0:
            role_in = None

    users, n_pages = db.users.find(
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
def query(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    field_name = next(iter(request.form.keys()))
    query = request.form.get(field_name)

    if query is None:
        raise exceptions.BadRequestException()
    
    if (role_in := request.args.get("role_id_in")) is not None:
        role_in = json.loads(role_in)
        try:
            role_in = [UserRole.get(int(role)) for role in role_in]
        except ValueError:
            raise exceptions.BadRequestException()
        
        if len(role_in) == 0:
            role_in = None

    only_insiders = request.args.get("only_insiders") == "True"
    results = db.users.query(query, role_in=role_in, only_insiders=only_insiders)
    
    return make_response(
        render_template(
            "components/search/user.html",
            results=results, field_name=field_name
        )
    )


@wrappers.htmx_route(users_htmx, db=db)
def table_query(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (word := request.args.get("last_name")) is not None:
        field_name = "last_name"
    elif (word := request.args.get("email")) is not None:
        field_name = "email"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()

    if (role_in := request.args.get("role_id_in")) is not None:
        role_in = json.loads(role_in)
        try:
            role_in = [UserRole.get(int(role)) for role in role_in]
        except ValueError:
            raise exceptions.BadRequestException()
        
        if len(role_in) == 0:
            role_in = None

    users: list[models.User] = []
    if field_name == "last_name":
        users = db.users.query(word, role_in=role_in)
    elif field_name == "email":
        users = db.users.query_with_email(word, role_in=role_in)
    elif field_name == "id":
        try:
            _id = int(word)
            if (user := db.users.get(_id)) is not None:
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
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if user.id != current_user.id and not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [ProjectStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
    
    projects, n_pages = db.projects.find(
        offset=offset, user_id=user_id, sort_by=sort_by,
        descending=descending, count_pages=True, status_in=status_in
    )
    
    return make_response(
        render_template(
            "components/tables/user-project.html",
            user=user, projects=projects,
            active_page=page, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order,
            status_in=status_in
        )
    )


@wrappers.htmx_route(users_htmx, db=db)
def get_seq_requests(current_user: models.User, user_id: int, page: int = 0):
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if user.id != current_user.id and not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SeqRequestStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
    
    seq_requests, n_pages = db.seq_requests.find(
        offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, status_in=status_in, count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/user-seq_request.html",
            user=user, seq_requests=seq_requests,
            active_page=page, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order,
        )
    )


@wrappers.htmx_route(users_htmx, db=db)
def query_seq_requests(current_user: models.User, user_id: int):
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()
    
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if user.id != current_user.id and not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SeqRequestStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    seq_requests: list[models.SeqRequest] = []
    if field_name == "name":
        seq_requests = db.seq_requests.query(word, user_id=user_id, status_in=status_in)
    elif field_name == "id":
        try:
            _id = int(word)
            if (seq_request := db.seq_requests.get(_id)) is not None:
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
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if user.id != current_user.id and not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "group_id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    affiliations, n_pages = db.users.get_affiliations(
        offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/user-affiliation.html",
            user=user, affiliations=affiliations,
            active_page=page, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order
        )
    )

@wrappers.htmx_route(users_htmx, db=db)
def get_api_tokens(current_user: models.User, user_id: int, page: int = 0):
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if user.id != current_user.id and not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "created_utc")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    tokens, n_pages = db.api_tokens.find(
        offset=offset, owner=user, sort_by=sort_by, descending=descending, count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/user-api_token.html",
            user=user, tokens=tokens,
            active_page=page, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order
        )
    )

@wrappers.htmx_route(users_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, user_id: int):
    if current_user.id != user_id and not current_user.is_admin():
        raise exceptions.NoPermissionsException()
    
    if (user := db.users.get(user_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return forms.models.UserForm(user=user, current_user=current_user).make_response()
    else:
        return forms.models.UserForm(user=user, current_user=current_user, formdata=request.form).process_request()