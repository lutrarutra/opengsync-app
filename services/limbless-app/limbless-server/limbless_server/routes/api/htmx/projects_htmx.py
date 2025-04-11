import json
from typing import Optional, TYPE_CHECKING

import numpy as np

from flask import Blueprint, url_for, render_template, flash, abort, request
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBHandler, PAGE_LIMIT, db_session
from limbless_db.categories import HTTPResponse, UserRole, SampleStatus, ProjectStatus

from .... import db, forms, logger
from ....tools import SpreadSheetColumn

if TYPE_CHECKING:
    current_user: models.User = None   # type: ignore
else:
    from flask_login import current_user

projects_htmx = Blueprint("projects_htmx", __name__, url_prefix="/api/hmtx/projects/")


@projects_htmx.route("get/<int:page>", methods=["GET"])
@projects_htmx.route("get", methods=["GET"], defaults={"page": 0})
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if sort_by not in models.Project.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    projects: list[models.Project] = []
    context = {}

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [ProjectStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    if (user_id := request.args.get("user_id", None)) is not None:
        template = "components/tables/user-project.html"
        try:
            user_id = int(user_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if user_id != current_user.id and not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (user := db.get_user(user_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        projects, n_pages = db.get_projects(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["user"] = user
    else:
        template = "components/tables/project.html"
        if not current_user.is_insider():
            user_id = current_user.id
        else:
            user_id = None
        projects, n_pages = db.get_projects(offset=offset, user_id=user_id, sort_by="id", descending=descending, count_pages=True, status_in=status_in)

    return make_response(
        render_template(
            template, projects=projects,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            status_in=status_in,
            **context
        )
    )


@projects_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if word is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if not current_user.is_insider():
        _user_id = current_user.id
    else:
        _user_id = None

    if (group_id := request.args.get("group_id", None)) is not None:
        try:
            group_id = int(group_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if (_ := db.get_group(group_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        _user_id = None

    results = db.query_projects(word, user_id=_user_id, group_id=group_id)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        )
    )


@projects_htmx.route("create", methods=["POST"])
@db_session(db)
@login_required
def create():
    return forms.models.ProjectForm(formdata=request.form).process_request(user=current_user)


@projects_htmx.route("<int:project_id>/edit", methods=["POST"])
@db_session(db)
@login_required
def edit(project_id: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    return forms.models.ProjectForm(project=project, formdata=request.form).process_request(
        user=current_user
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
@db_session(db)
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
        if (user := db.get_user(user_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
            
        projects = __get_projects(db, word, field_name, user_id=user_id)
        context["user"] = user
    else:
        template = "components/tables/project.html"

        if not current_user.is_insider():
            user_id = current_user.id
        else:
            user_id = None
        projects = __get_projects(db, word, field_name, user_id=user_id)

    return make_response(
        render_template(
            template, current_query=word, field_name=field_name,
            projects=projects, **context
        )
    )
        

@projects_htmx.route("<int:project_id>/get_samples", methods=["GET"], defaults={"page": 0})
@projects_htmx.route("<int:project_id>/get_samples/<int:page>", methods=["GET"])
@login_required
def get_samples(project_id: int, page: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    samples, n_pages = db.get_samples(offset=offset, project_id=project_id, sort_by=sort_by, descending=descending, status_in=status_in, count_pages=True)

    return make_response(
        render_template(
            "components/tables/project-sample.html", samples=samples,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            project=project, status_in=status_in
        )
    )


@projects_htmx.route("<int:project_id>/query_samples/<string:field_name>", methods=["POST"])
@login_required
def query_samples(project_id: int, field_name: str):
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    samples = []
    if field_name == "name":
        samples = db.query_samples(word, project_id=project_id)
    elif field_name == "id":
        try:
            if (sample := db.get_sample(int(word))) is not None:
                if sample.project_id == project_id:
                    samples = [sample]
        except ValueError:
            samples = []
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)

    return make_response(
        render_template(
            "components/tables/project-sample.html",
            samples=samples, field_name=field_name, project=project
        )
    )


@projects_htmx.route("<int:project_id>/get_sample_attributes", methods=["GET"])
@login_required
def get_sample_attributes(project_id: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    df = db.get_project_sample_attributes_df(project_id=project_id)

    columns = []
    for i, col in enumerate(df.columns):
        if "id" == col:
            width = 50
        elif "name" == col:
            width = 300
        else:
            width = 150
        columns.append(SpreadSheetColumn(col, col.replace("_", " ").title(), "text", width, var_type=str))

    return make_response(
        render_template(
            "components/itable.html",
            spreadsheet_data=df.replace({np.nan: ""}).values.tolist(),
            columns=columns,
            table_id="sample-attribute-table"
        )
    )


@projects_htmx.route("<int:project_id>/edit_sample_attributes", methods=["GET", "POST"])
@login_required
def edit_sample_attributes(project_id: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    if request.method == "GET":
        form = forms.SampleAttributeTableForm(project)
        return form.make_response()
    elif request.method == "POST":
        return forms.SampleAttributeTableForm(project=project, formdata=request.form).process_request()
    
    return abort(HTTPResponse.METHOD_NOT_ALLOWED.id)


@projects_htmx.route("get_recent_projects", methods=["GET"])
@db_session(db)
@login_required
def get_recent_projects():
    status_in = None
    if current_user.is_insider():
        status_in = [
            ProjectStatus.PROCESSING,
            ProjectStatus.DELIVERED,
            ProjectStatus.ARCHIVED
        ]

    projects, _ = db.get_projects(
        user_id=current_user.id if not current_user.is_insider() else None,
        sort_by="id", limit=15,
        status_in=status_in, descending=True
    )

    return make_response(
        render_template(
            "components/dashboard/projects-list.html", projects=projects
        )
    )