from typing import Optional

from flask import Blueprint, url_for, render_template, flash, abort, request
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, forms, logger, models
from ....core import DBSession, DBHandler
from ....categories import UserRole, HttpResponse

projects_htmx = Blueprint("projects_htmx", __name__, url_prefix="/api/projects/")


@projects_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    reversed = order == "desc"

    if sort_by not in models.Project.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    projects: list[models.Project] = []
    context = {}

    if (user_id := request.args.get("user_id", None)) is not None:
        template = "components/tables/user-project.html"
        try:
            user_id = int(user_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        if user_id != current_user.id and not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        with DBSession(db.db_handler) as session:
            if (user := session.get_user(user_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            
            projects, n_pages = session.get_projects(limit=20, user_id=user_id, sort_by=sort_by, reversed=reversed)
            context["user"] = user
    else:
        template = "components/tables/project.html"
        with DBSession(db.db_handler) as session:
            if not current_user.is_insider():
                user_id = current_user.id
            else:
                user_id = None
            projects, n_pages = session.get_projects(limit=20, user_id=user_id, sort_by="id", reversed=reversed)

    return make_response(
        render_template(
            template, projects=projects,
            n_pages=n_pages, active_page=page,
            current_sort=sort_by, current_sort_order=order,
            **context
        ), push_url=False
    )


@projects_htmx.route("create", methods=["POST"])
@login_required
def create():
    project_form = forms.ProjectForm()
    validated, project_form = project_form.custom_validate(db.db_handler, current_user.id)

    if not validated:
        template = render_template(
            "forms/project.html",
            project_form=project_form
        )
        return make_response(
            template, push_url=False
        )

    with DBSession(db.db_handler) as session:
        project = session.create_project(
            name=project_form.name.data,
            description=project_form.description.data,
            owner_id=current_user.id
        )

    logger.debug(f"Created project {project.name}.")
    flash(f"Created project {project.name}.", "success")

    return make_response(
        redirect=url_for("projects_page.project_page", project_id=project.id),
    )

# TODO: edit project


@projects_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    if (word := request.form.get("name", None)) is not None:
        field_name = "name"
    elif (word := request.form.get("id", None)) is not None:
        field_name = "id"
    else:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if word is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

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
            return abort(HttpResponse.BAD_REQUEST.value.id)
        with DBSession(db.db_handler) as session:
            if (user := session.get_user(user_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            
            projects = __get_projects(session, word, field_name, user_id=user_id)
            context["user"] = user
    else:
        template = "components/tables/project.html"

        with DBSession(db.db_handler) as session:
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
        