from flask import Blueprint, render_template, redirect, abort
from flask_login import login_required, current_user

from ... import db, forms, logger
from ...core import DBSession
from ...categories import UserRole

projects_page_bp = Blueprint("projects_page", __name__)


@projects_page_bp.route("/projects")
@login_required
def projects_page():
    project_form = forms.ProjectForm()

    with DBSession(db.db_handler) as session:
        if current_user.role_type == UserRole.CLIENT:
            projects = session.get_projects(limit=20, user_id=current_user.id)
            n_pages = int(session.get_num_projects(user_id=current_user.id) / 20)
        else:
            projects = session.get_projects(limit=20, user_id=None)
            n_pages = int(session.get_num_projects(user_id=None) / 20)

    return render_template(
        "projects_page.html", project_form=project_form,
        projects=projects, n_pages=n_pages, active_page=0
    )


@projects_page_bp.route("/projects/<project_id>")
@login_required
def project_page(project_id):
    with DBSession(db.db_handler) as session:
        if (project := session.get_project(project_id)) is None:
            return abort(404)
        access = session.get_user_project_access(current_user.id, project_id)
        if access is None:
            return abort(403)

        samples = session.get_project_samples(project_id)

    table_form = forms.TableForm()

    return render_template(
        "project_page.html", project=project,
        sample_form=forms.SampleForm(),
        samples=samples,
        table_form=table_form,
        sample_results=db.common_organisms
    )
