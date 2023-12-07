from flask import Blueprint, render_template, redirect, abort, url_for
from flask_login import login_required, current_user

from ... import db, forms, logger, PAGE_LIMIT
from ...core import DBSession
from ...categories import UserRole, HttpResponse

projects_page_bp = Blueprint("projects_page", __name__)


@projects_page_bp.route("/projects")
@login_required
def projects_page():
    project_form = forms.ProjectForm()

    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            projects, n_pages = session.get_projects(limit=PAGE_LIMIT, user_id=current_user.id, sort_by="id", descending=True)
        else:
            projects, n_pages = session.get_projects(limit=PAGE_LIMIT, user_id=None, sort_by="id", descending=True)

        return render_template(
            "projects_page.html", project_form=project_form,
            projects=projects, projects_n_pages=n_pages, projects_active_page=0,
            current_sort="id", current_sort_order="desc"
        )


@projects_page_bp.route("/projects/<project_id>")
@login_required
def project_page(project_id):
    with DBSession(db.db_handler) as session:
        if (project := session.get_project(project_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        access = session.get_user_project_access(current_user.id, project_id)
        if access is None:
            return abort(HttpResponse.FORBIDDEN.value.id)

        samples, n_pages = session.get_samples(project_id=project_id, sort_by="id", descending=True)

    path_list = [
        ("Projects", url_for("projects_page.projects_page")),
        (f"Project {project_id}", ""),
    ]

    return render_template(
        "project_page.html", project=project,
        samples=samples,
        path_list=path_list,
        common_organisms=db.common_organisms,
        samples_n_pages=n_pages, samples_active_page=0,
    )
