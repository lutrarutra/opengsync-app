from flask import Blueprint, render_template, abort, url_for
from flask_login import login_required, current_user

from limbless_db import DBSession
from limbless_db.core.categories import HttpResponse
from ... import db, forms

projects_page_bp = Blueprint("projects_page", __name__)


@projects_page_bp.route("/projects")
@login_required
def projects_page():
    project_form = forms.ProjectForm()

    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            projects, n_pages = session.get_projects(user_id=current_user.id, sort_by="id", descending=True)
        else:
            projects, n_pages = session.get_projects(user_id=None, sort_by="id", descending=True)

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
        if not current_user.is_insider() and project.owner_id != current_user.id:
            return abort(HttpResponse.FORBIDDEN.value.id)

        samples, n_pages = session.get_samples(project_id=project_id, sort_by="id", descending=True)

    path_list = [
        ("Projects", url_for("projects_page.projects_page")),
        (f"Project {project_id}", ""),
    ]

    project_form = forms.ProjectForm(project=project)

    return render_template(
        "project_page.html", project=project,
        samples=samples,
        path_list=path_list,
        project_form=project_form,
        common_organisms=db.common_organisms,
        samples_n_pages=n_pages, samples_active_page=0,
    )
