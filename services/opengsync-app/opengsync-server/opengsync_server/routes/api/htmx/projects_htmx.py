import json

import numpy as np
import pandas as pd

from flask import Blueprint, url_for, render_template, flash, abort, request
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import HTTPResponse, SampleStatus, ProjectStatus, LibraryStatus, SeqRequestStatus

from .... import db, forms, logger
from ....core import wrappers
from ....tools.spread_sheet_components import TextColumn

projects_htmx = Blueprint("projects_htmx", __name__, url_prefix="/api/hmtx/projects/")


@wrappers.htmx_route(projects_htmx, db=db)
def get(current_user: models.User, page: int = 0):
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
        projects, n_pages = db.get_projects(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)

    return make_response(
        render_template(
            template, projects=projects,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            status_in=status_in,
            **context
        )
    )


@wrappers.htmx_route(projects_htmx, db=db, methods=["POST"])
def query(current_user: models.User):
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name, default="")) is None:
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
            
    results = db.query_projects(identifier_title=word, user_id=_user_id, group_id=group_id)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        )
    )


@wrappers.htmx_route(projects_htmx, db=db, methods=["POST"])
def create(current_user: models.User):
    return forms.models.ProjectForm(formdata=request.form).process_request(user=current_user)


@wrappers.htmx_route(projects_htmx, db=db, methods=["POST"])
def edit(current_user: models.User, project_id: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    return forms.models.ProjectForm(project=project, formdata=request.form).process_request(
        user=current_user
    )


@wrappers.htmx_route(projects_htmx, db=db, methods=["DELETE"])
def delete(current_user: models.User, project_id: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if project.owner_id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    if project.num_samples > 0:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    db.delete_project(project_id)
    flash(f"Deleted project {project.title}.", "success")
    return make_response(redirect=url_for("projects_page.projects"))


@wrappers.htmx_route(projects_htmx, db=db, methods=["POST"])
def complete(current_user: models.User, project_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    for library in project.libraries:
        if library.status not in {LibraryStatus.SHARED, LibraryStatus.FAILED, LibraryStatus.REJECTED, LibraryStatus.ARCHIVED}:
            flash(f"Cannot complete project {project.title} because some libraries are not shared/failed/rejected/archived.", "warning")
            return make_response(redirect=url_for("projects_page.project", project_id=project_id))
            
    project.status = ProjectStatus.DELIVERED
    project = db.update_project(project)
    return make_response(redirect=url_for("projects_page.project", project_id=project.id))


@wrappers.htmx_route(projects_htmx, db=db)
def table_query(current_user: models.User):
    id = None
    title = None
    if (identifier := request.args.get("identifier", None)) is not None:
        field_name = "identifier"
    elif (title := request.args.get("title", None)) is not None:
        field_name = "title"
    elif (id := request.args.get("id", None)) is not None:
        field_name = "id"
        try:
            id = int(id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)

    def __get_projects(
        title: str | None = None,
        identifier: str | None = None,
        id: int | None = None,
        user_id: int | None = None
    ) -> list[models.Project]:
        projects: list[models.Project] = []
        if id is not None:
            try:
                if (project := db.get_project(id)) is not None:
                    if user_id is not None:
                        if project.owner_id == user_id:
                            projects = [project]
                    else:
                        projects = [project]
            except ValueError:
                pass
        else:
            projects = db.query_projects(title=title, identifier=identifier, user_id=user_id)

        return projects
    
    context = {}
    if (user_id := request.args.get("user_id", None)) is not None:
        logger.error("User-specific project queries are not implemented yet.")
        raise NotImplementedError("User-specific project queries are not implemented yet.")
        template = "components/tables/user-project.html"
        try:
            user_id = int(user_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        if (user := db.get_user(user_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
            
        context["user"] = user
    else:
        template = "components/tables/project.html"

        if not current_user.is_insider():
            user_id = current_user.id
        else:
            user_id = None

    projects = __get_projects(title=title, identifier=identifier, id=id, user_id=user_id)

    return make_response(
        render_template(
            template,
            current_query=identifier or title or id,
            field_name=field_name,
            projects=projects, **context
        )
    )


@wrappers.htmx_route(projects_htmx, db=db)
def get_seq_requests(current_user: models.User, project_id: int, page: int = 0):
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

    if sort_by not in models.SeqRequest.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SeqRequestStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
    
    seq_requests, n_pages = db.get_seq_requests(
        offset=offset, project_id=project_id, sort_by=sort_by, descending=descending, status_in=status_in, count_pages=True
    )
    return make_response(
        render_template(
            "components/tables/project-seq_request.html",
            seq_requests=seq_requests,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            project=project, status_in=status_in
        )
    )
        

@wrappers.htmx_route(projects_htmx, db=db)
def get_samples(current_user: models.User, project_id: int, page: int = 0):
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


@wrappers.htmx_route(projects_htmx, db=db, methods=["POST"])
def query_samples(current_user: models.User, project_id: int, field_name: str):
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


@wrappers.htmx_route(projects_htmx, db=db)
def get_sample_attributes(current_user: models.User, project_id: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    df = db.get_project_samples_df(project_id=project_id).rename(columns={"sample_id": "id", "sample_name": "name"})

    columns = []
    for i, col in enumerate(df.columns):
        if "id" == col:
            width = 50
        elif "name" == col:
            width = 300
        else:
            width = 150
        columns.append(TextColumn(col, col.replace("_", " ").title(), width, max_length=1000))

    return make_response(
        render_template(
            "components/itable.html",
            spreadsheet_data=df.replace({np.nan: ""}).values.tolist(),
            columns=columns,
            table_id="sample-attribute-table"
        )
    )


@wrappers.htmx_route(projects_htmx, db=db, methods=["GET", "POST"])
def edit_sample_attributes(current_user: models.User, project_id: int):
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


@wrappers.htmx_route(projects_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get_recent_projects(current_user: models.User):
    status_in = None
    if current_user.is_insider():
        status_in = [
            ProjectStatus.PROCESSING,
            ProjectStatus.SEQUENCED,
            ProjectStatus.DELIVERED,
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


@wrappers.htmx_route(projects_htmx, db=db)
def get_software(current_user: models.User, project_id: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)

    software = project.software or {}
    return make_response(
        render_template(
            "components/project-software.html",
            software=software,
            project=project,
        )
    )


@wrappers.htmx_route(projects_htmx, db=db)
def overview(current_user: models.User, project_id: int):
    if (project := db.get_project(project_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
        
    df = db.get_project_libraries_df(project_id=project_id)

    LINK_WIDTH_UNIT = 0.5

    nodes = []
    links = []
    experiment_nodes = {}
    seq_request_nodes = {}
    idx = 0

    for (sample_name,), sample_df in df.groupby(["sample_name"]):
        sample_node = {
            "node": idx,
            "name": sample_name,
        }
        idx += 1
        nodes.append(sample_node)
        for _, row in sample_df.iterrows():
            library_name = row["library_name"]
            seq_request_id = row["seq_request_id"]
            experiment_name = row["experiment_name"] if pd.notna(row["experiment_name"]) else None

            library_in_node = {
                "node": idx,
                "name": library_name,
            }
            idx += 1
            nodes.append(library_in_node)
            links.append({
                "source": sample_node["node"],
                "target": library_in_node["node"],
                "value": LINK_WIDTH_UNIT
            })

            if seq_request_id not in seq_request_nodes:
                seq_request_node = {
                    "node": idx,
                    "name": f"Request {seq_request_id}",
                }
                idx += 1
                nodes.append(seq_request_node)
                seq_request_nodes[seq_request_id] = seq_request_node["node"]

            links.append({
                "source": library_in_node["node"],
                "target": seq_request_nodes[seq_request_id],
                "value": LINK_WIDTH_UNIT
            })

            if experiment_name is not None:
                if experiment_name not in experiment_nodes:
                    experiment_node = {
                        "node": idx,
                        "name": experiment_name,
                    }
                    idx += 1
                    nodes.append(experiment_node)
                    experiment_nodes[experiment_name] = experiment_node["node"]
                
                library_out_node = {
                    "node": idx,
                    "name": library_name,
                }
                idx += 1
                nodes.append(library_out_node)
                links.append({
                    "source": seq_request_nodes[seq_request_id],
                    "target": library_out_node["node"],
                    "value": LINK_WIDTH_UNIT
                })
                links.append({
                    "source": library_out_node["node"],
                    "target": experiment_nodes[experiment_name],
                    "value": LINK_WIDTH_UNIT
                })

    return make_response(
        render_template(
            "components/plots/project_overview.html",
            nodes=nodes, links=links,
        )
    )