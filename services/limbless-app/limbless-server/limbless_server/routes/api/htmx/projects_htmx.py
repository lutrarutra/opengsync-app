from typing import Optional, TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, abort, request
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, DBHandler, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, UserRole
from .... import db, forms

if TYPE_CHECKING:
    current_user: models.User = None   # type: ignore
else:
    from flask_login import current_user

projects_htmx = Blueprint("projects_htmx", __name__, url_prefix="/api/hmtx/projects/")


@projects_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = page * PAGE_LIMIT

    if sort_by not in models.Project.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    projects: list[models.Project] = []
    context = {}

    if (user_id := request.args.get("user_id", None)) is not None:
        template = "components/tables/user-project.html"
        try:
            user_id = int(user_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if user_id != current_user.id and not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        with DBSession(db) as session:
            if (user := session.get_user(user_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            
            projects, n_pages = session.get_projects(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending)
            context["user"] = user
    else:
        template = "components/tables/project.html"
        with DBSession(db) as session:
            if not current_user.is_insider():
                user_id = current_user.id
            else:
                user_id = None
            projects, n_pages = session.get_projects(offset=offset, user_id=user_id, sort_by="id", descending=descending)

    return make_response(
        render_template(
            template, projects=projects,
            projects_n_pages=n_pages, projects_active_page=page,
            current_sort=sort_by, current_sort_order=order,
            **context
        ), push_url=False
    )


@projects_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if word is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if current_user.role == UserRole.CLIENT:
        _user_id = current_user.id
    else:
        _user_id = None

    results = db.query_projects(word, user_id=_user_id)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )


@projects_htmx.route("create", methods=["POST"])
@login_required
def create():
    return forms.ProjectForm(request.form).process_request(user_id=current_user.id)


@projects_htmx.route("<int:project_id>/edit", methods=["POST"])
@login_required
def edit(project_id: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if project.owner_id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    return forms.ProjectForm(request.form).process_request(
        user_id=current_user.id, project=project
    )


@projects_htmx.route("<int:project_id>/delete", methods=["DELETE"])
@login_required
def delete(project_id: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if project.owner_id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    if project.num_samples > 0:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    db.delete_project(project_id)
    flash(f"Deleted project {project.name}.", "success")
    return make_response(redirect=url_for("projects_page.projects_page"))


@projects_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    if (word := request.form.get("name", None)) is not None:
        field_name = "name"
    elif (word := request.form.get("id", None)) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if word is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    def __get_projects(
        session: DBHandler, word: str | int, field_name: str,
        user_id: Optional[int] = None
    ) -> list[models.Project]:
        projects: list[models.Project] = []
        if field_name == "name":
            projects = session.query_projects(
                str(word), user_id=user_id
            )
        elif field_name == "id":
            try:
                _id = int(word)
                if (project := session.get_project(_id)) is not None:
                    if user_id is not None:
                        if project.owner_id == user_id:
                            projects = [project]
                    else:
                        projects = [project]
            except ValueError:
                pass
        else:
            assert False    # This should never happen

        return projects
    
    context = {}
    if (user_id := request.args.get("user_id", None)) is not None:
        template = "components/tables/user-project.html"
        try:
            user_id = int(user_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        with DBSession(db) as session:
            if (user := session.get_user(user_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            
            projects = __get_projects(session, word, field_name, user_id=user_id)
            context["user"] = user
    else:
        template = "components/tables/project.html"

        with DBSession(db) as session:
            if not current_user.is_insider():
                user_id = current_user.id
            else:
                user_id = None
            projects = __get_projects(session, word, field_name, user_id=user_id)

    return make_response(
        render_template(
            template, current_query=word, field_name=field_name,
            projects=projects, **context
        ), push_url=False
    )
        