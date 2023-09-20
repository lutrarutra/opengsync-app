from flask import Blueprint, url_for, render_template, flash
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, forms, logger
from ....categories import UserResourceRelation
from ....core import DBSession

projects_htmx = Blueprint("projects_htmx", __name__, url_prefix="/api/projects/")


@projects_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page):
    with DBSession(db.db_handler) as session:
        n_pages = int(session.get_num_projects() / 20)
        page = min(page, n_pages)
        projects = session.get_projects(limit=20, offset=20 * page)

    return make_response(
        render_template(
            "components/tables/project.html", projects=projects,
            n_pages=n_pages, active_page=page
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
