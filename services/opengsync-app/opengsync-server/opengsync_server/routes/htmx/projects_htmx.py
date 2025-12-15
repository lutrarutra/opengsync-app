import json
from io import BytesIO

import pandas as pd

from flask import Blueprint, url_for, render_template, flash, request, Response
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import SampleStatus, ProjectStatus, LibraryStatus, SeqRequestStatus, AccessType, DataPathType, ExperimentStatus

from ... import db, forms, logger, logic
from ...core import wrappers, exceptions
from ...tools.spread_sheet_components import TextColumn
from ...tools import StaticSpreadSheet

projects_htmx = Blueprint("projects_htmx", __name__, url_prefix="/htmx/projects/")


@wrappers.htmx_route(projects_htmx, db=db, cache_timeout_seconds=120, cache_type="insider")
def get(current_user: models.User):    
    context = logic.tables.render_project_table(current_user=current_user, request=request)
    return make_response(render_template(**context))


@wrappers.htmx_route(projects_htmx, db=db, methods=["POST"])
def query(current_user: models.User):
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name, default="")) is None:
        raise exceptions.BadRequestException()

    if not current_user.is_insider():
        _user_id = current_user.id
    else:
        _user_id = None

    if (group_id := request.args.get("group_id", None)) is not None:
        try:
            group_id = int(group_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (_ := db.groups.get(group_id)) is None:
            raise exceptions.NotFoundException()
        
        _user_id = None
            
    results = db.projects.query(identifier_title=word, user_id=_user_id, group_id=group_id)

    return make_response(
        render_template(
            "components/search/project.html",
            results=results,
            field_name=field_name
        )
    )

@wrappers.htmx_route(projects_htmx, db=db, methods=["GET", "POST"])
def create(current_user: models.User):
    if request.method == "GET":
        return forms.models.ProjectForm(
            project=None,
            form_type="create",
        ).make_response()
    
    return forms.models.ProjectForm(
        project=None,
        form_type="create",
        formdata=request.form
    ).process_request(user=current_user)


@wrappers.htmx_route(projects_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.projects.get_access_type(project, current_user)

    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    if project.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        return forms.models.ProjectForm(project=project, form_type="edit").make_response()
    
    return forms.models.ProjectForm(
        project=project, form_type="edit", formdata=request.form,
    ).process_request(user=current_user)


@wrappers.htmx_route(projects_htmx, db=db, methods=["DELETE"])
def delete(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.projects.get_access_type(project, current_user)

    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    if project.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()

    if project.num_samples > 0:
        raise exceptions.BadRequestException()
    
    db.projects.delete(project_id)
    flash(f"Deleted project {project.title}.", "success")
    return make_response(redirect=url_for("projects_page.projects"))


@wrappers.htmx_route(projects_htmx, db=db, methods=["POST"])
def complete(current_user: models.User, project_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    for library in project.libraries:
        if library.status not in {LibraryStatus.SHARED, LibraryStatus.FAILED, LibraryStatus.REJECTED, LibraryStatus.ARCHIVED}:
            flash(f"Cannot complete project {project.title} because some libraries are not shared/failed/rejected/archived.", "warning")
            return make_response(redirect=url_for("projects_page.project", project_id=project_id))
            
    project.status = ProjectStatus.DELIVERED
    db.projects.update(project)
    return make_response(redirect=url_for("projects_page.project", project_id=project.id))


@wrappers.htmx_route(projects_htmx, db=db)
def table_query(current_user: models.User):
    id = None
    title = None
    owner_name = None

    if (identifier := request.args.get("identifier", None)) is not None:
        field_name = "identifier"
    elif (title := request.args.get("title", None)) is not None:
        field_name = "title"
    elif (id := request.args.get("id", None)) is not None:
        field_name = "id"
        try:
            id = int(id)
        except ValueError:
            raise exceptions.BadRequestException()
    elif (owner_name := request.args.get("owner_id", None)) is not None:
        field_name = "owner_id"
    else:
        raise exceptions.BadRequestException()

    def __get_projects(
        title: str | None = None,
        identifier: str | None = None,
        id: int | None = None,
        user_id: int | None = None,
        owner_name: str | None = None,
    ) -> list[models.Project]:
        projects: list[models.Project] = []
        if id is not None:
            try:
                if (project := db.projects.get(id)) is not None:
                    if user_id is not None:
                        if project.owner_id == user_id:
                            projects = [project]
                    else:
                        projects = [project]
            except ValueError:
                pass
        else:
            projects = db.projects.query(title=title, identifier=identifier, user_id=user_id, owner_name=owner_name)

        return projects
    
    context = {}
    if (user_id := request.args.get("user_id", None)) is not None:
        logger.error("User-specific project queries are not implemented yet.")
        raise NotImplementedError("User-specific project queries are not implemented yet.")
        template = "components/tables/user-project.html"
        try:
            user_id = int(user_id)
        except ValueError:
            raise exceptions.BadRequestException()
        if (user := db.users.get(user_id)) is None:
            raise exceptions.NotFoundException()
            
        context["user"] = user
    else:
        template = "components/tables/project.html"

        if not current_user.is_insider():
            user_id = current_user.id
        else:
            user_id = None

    projects = __get_projects(title=title, identifier=identifier, owner_name=owner_name, id=id, user_id=user_id)

    return make_response(
        render_template(
            template,
            current_query=identifier or title or id or owner_name,
            field_name=field_name,
            projects=projects, **context
        )
    )


@wrappers.htmx_route(projects_htmx, db=db)
def get_experiments(current_user: models.User, project_id: int, page: int = 0):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()

    if not current_user.is_insider() and project.owner_id != current_user.id:
        affiliation = db.groups.get_user_affiliation(user_id=current_user.id, group_id=project.group_id) if project.group_id else None
        if affiliation is None:
            raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if sort_by not in models.SeqRequest.sortable_fields:
        raise exceptions.BadRequestException()

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [ExperimentStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
    
    experiments, n_pages = db.experiments.find(
        offset=offset, project_id=project_id, sort_by=sort_by, descending=descending, status_in=status_in, count_pages=True
    )
    return make_response(
        render_template(
            "components/tables/project-experiment.html",
            experiments=experiments,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            project=project, status_in=status_in
        )
    )


@wrappers.htmx_route(projects_htmx, db=db)
def get_data_paths(current_user: models.User, project_id: int, page: int = 0):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()

    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [DataPathType.get(int(t)) for t in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    data_paths, n_pages = db.data_paths.find(offset=offset, project_id=project_id, type_in=type_in, sort_by=sort_by, descending=descending, count_pages=True)

    return make_response(
        render_template(
            "components/tables/project-data_path.html", data_paths=data_paths,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            project=project, type_in=type_in
        )
    )


@wrappers.htmx_route(projects_htmx, db=db, methods=["POST"])
def query_samples(current_user: models.User, project_id: int, field_name: str):
    if (word := request.form.get(field_name)) is None:
        raise exceptions.BadRequestException()
    
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    samples = []
    if field_name == "name":
        samples = db.samples.query(word, project_id=project_id)
    elif field_name == "id":
        try:
            if (sample := db.samples.get(int(word))) is not None:
                if sample.project_id == project_id:
                    samples = [sample]
        except ValueError:
            samples = []
    else:
        raise exceptions.BadRequestException()

    return make_response(
        render_template(
            "components/tables/project-sample.html",
            samples=samples, field_name=field_name, project=project
        )
    )


@wrappers.htmx_route(projects_htmx, db=db)
def get_sample_attributes(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()

    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    df = db.pd.get_project_samples(project_id=project_id).rename(columns={"sample_id": "id", "sample_name": "name"})

    columns = []
    for col in df.columns:
        if "id" == col:
            width = 50
        elif "name" == col:
            width = 300
        else:
            width = 150
        columns.append(TextColumn(col, col.replace("_", " ").title(), width, max_length=1000))

    spreadsheet = StaticSpreadSheet(df, columns=columns, id="sample-attribute-table")

    return make_response(render_template("components/itable.html", spreadsheet=spreadsheet))

@wrappers.htmx_route(projects_htmx, db=db)
def render_sample_table(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()

    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    if project.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    df = db.pd.get_project_samples(project_id=project_id)

    columns: list = [
        TextColumn("sample_name", "Sample Name", 400, read_only=True),
    ]

    spreadsheet = StaticSpreadSheet(df, columns=columns, id="sample-attribute-table")
    
    return make_response(render_template("components/itable.html", spreadsheet=spreadsheet))


@wrappers.htmx_route(projects_htmx, db=db, methods=["GET", "POST"])
def edit_sample_attributes(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    if project.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()

    if request.method == "GET":
        form = forms.SampleAttributeTableForm(project)
        return form.make_response()
    elif request.method == "POST":
        return forms.SampleAttributeTableForm(project=project, formdata=request.form).process_request()
    
    raise exceptions.MethodNotAllowedException()


@wrappers.htmx_route(projects_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get_recent_projects(current_user: models.User, page: int = 0):
    PAGE_LIMIT = 10
    status_in = None
    if current_user.is_insider():
        status_in = [
            ProjectStatus.PROCESSING, ProjectStatus.SEQUENCED,
        ]

    projects, _ = db.projects.find(
        user_id=current_user.id if not current_user.is_insider() else None,
        sort_by="id", status_in=status_in, descending=True,
        limit=PAGE_LIMIT, offset=PAGE_LIMIT * page
    )

    return make_response(
        render_template(
            "components/dashboard/projects-list.html", projects=projects,
            current_page=page, limit=PAGE_LIMIT
        )
    )


@wrappers.htmx_route(projects_htmx, db=db)
def get_software(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()

    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
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
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()

    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
        
    df = db.pd.get_project_libraries(project_id=project_id)

    LINK_WIDTH_UNIT = 1

    nodes = []
    links = []
    library_in_nodes = {}
    library_out_nodes = {}

    experiment_nodes = {}
    seq_request_nodes = {}
    idx = 0

    for (experiment_name,), _ in df.groupby(["experiment_name"]):
        node = {
            "node": idx,
            "name": experiment_name,
        }
        experiment_nodes[experiment_name] = node
        nodes.append(node)
        idx += 1

    for (seq_request_id,), _ in df.groupby(["seq_request_id",]):
        node = {
            "node": idx,
            "name": f"Request {seq_request_id}",
        }
        seq_request_nodes[seq_request_id] = node
        nodes.append(node)
        idx += 1

    for (sample_name,), sample_df in df.groupby(["sample_name"]):
        sample_node = {
            "node": idx,
            "name": sample_name,
        }
        idx += 1
        nodes.append(sample_node)

        for _, row in sample_df.iterrows():
            library_name = row["library_name"]
            library_id = row["library_id"]
            seq_request_id = row["seq_request_id"]
            experiment_name = row["experiment_name"] if pd.notna(row["experiment_name"]) else None

            if library_id not in library_in_nodes:
                library_in_node = {
                    "node": idx,
                    "name": library_name,
                }
                idx += 1
                nodes.append(library_in_node)
                library_in_nodes[library_id] = library_in_node
                links.append({
                    "source": library_in_node["node"],
                    "target": seq_request_nodes[seq_request_id]["node"],
                    "value": LINK_WIDTH_UNIT * len(df[df["library_id"] == library_id])
                })
            else:
                library_in_node = library_in_nodes[library_id]

            links.append({
                "source": sample_node["node"],
                "target": library_in_node["node"],
                "value": LINK_WIDTH_UNIT
            })

            if experiment_name is not None:
                if library_id not in library_out_nodes:
                    library_out_node = {
                        "node": idx,
                        "name": library_name,
                    }
                    idx += 1
                    nodes.append(library_out_node)
                    library_out_nodes[library_id] = library_out_node
                    links.append({
                        "source": library_out_node["node"],
                        "target": experiment_nodes[experiment_name]["node"],
                        "value": LINK_WIDTH_UNIT * len(df[df["library_id"] == library_id])
                    })
                    links.append({
                        "source": seq_request_nodes[seq_request_id]["node"],
                        "target": library_out_node["node"],
                        "value": LINK_WIDTH_UNIT * len(df[(df["library_id"] == library_id) & (df["seq_request_id"] == seq_request_id)])
                    })
    
    return make_response(
        render_template(
            "components/plots/project_overview.html",
            nodes=nodes, links=links,
        )
    )


@wrappers.htmx_route(projects_htmx, db=db, methods=["DELETE"])
def remove_data_path(current_user: models.User, project_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (data_path_id := request.args.get("data_path_id", None)) is None:
        raise exceptions.BadRequestException()
    
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()

    try:
        data_path_id = int(data_path_id)
    except ValueError:
        raise exceptions.BadRequestException()
    
    if (data_path := db.data_paths.get(data_path_id)) is None:
        raise exceptions.NotFoundException()
    
    if data_path.project_id != project.id:
        raise exceptions.BadRequestException()
    
    db.data_paths.delete(data_path)

    flash("Path Removed.", "success")
    return make_response(redirect=url_for("projects_page.project", project_id=project.id, tab="project-data_paths-tab"))

        
@wrappers.htmx_route(projects_htmx, db=db)
def get_assignees(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    return make_response(
        render_template(
            "components/tables/project-assignee.html",
            assignees=project.assignees,
            project=project
        )
    )

@wrappers.htmx_route(projects_htmx, db=db, methods=["POST"])
def add_assignee(current_user: models.User, project_id: int, assignee_id: int | None = None):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if assignee_id is not None:
        if (assignee := db.users.get(assignee_id)) is None:
            raise exceptions.NotFoundException()
    else:
        assignee = current_user
    
    if not assignee.is_insider():
        raise exceptions.NoPermissionsException("Assignee must be an insider.")
    
    if assignee in project.assignees:
        raise exceptions.BadRequestException("User is already an assignee.")
    
    project.assignees.append(assignee)
    db.projects.update(project)

    flash("Assignee Added!", "success")
    if request.args.get("context") == "dashboard":
        return make_response(redirect=url_for("dashboard"))
    else:
        return make_response(render_template(**logic.tables.render_project_table(current_user=current_user, request=request)))

@wrappers.htmx_route(projects_htmx, db=db, methods=["GET", "POST"])
def add_assignee_form(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        form = forms.AddProjectAssigneeForm(current_user=current_user, project=project)
        return form.make_response()
    else:
        return forms.AddProjectAssigneeForm(formdata=request.form, current_user=current_user, project=project).process_request()

@wrappers.htmx_route(projects_htmx, db=db, methods=["DELETE"])
def remove_assignee(current_user: models.User, project_id: int, assignee_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (assignee := db.users.get(assignee_id)) is None:
        raise exceptions.NotFoundException()
    
    if assignee not in project.assignees:
        raise exceptions.BadRequestException()

    project.assignees.remove(assignee)
    db.projects.update(project)

    flash("Assignee Removed.", "success")

    return make_response(
        render_template(
            "components/tables/project-assignee.html",
            assignees=project.assignees,
            project=project
        )
    )

@wrappers.htmx_route(projects_htmx, db=db, methods=["GET"])
def export(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    metadata = pd.DataFrame.from_records({
        "Project ID": [project.id],
        "Project Identifier": [project.identifier],
        "Project Title": [project.title],
        "Owner": [project.owner.name],
        "Created At": [project.timestamp_created.isoformat()],
        "Status": [project.status.name],
        "Group": [project.group.name if project.group else "N/A"],
        "Number of Samples": [project.num_samples],
    }).T

    samples_df = db.pd.get_project_samples(project_id=project.id)
    libraries_df = db.pd.get_project_libraries(project_id=project.id)
    seq_requests_df = db.pd.get_project_seq_requests(project_id=project.id)

    bytes_io = BytesIO()

    with pd.ExcelWriter(bytes_io, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="Metadata")
        samples_df.to_excel(writer, sheet_name="Samples", index=False)
        libraries_df.to_excel(writer, sheet_name="Libraries", index=False)
        seq_requests_df.to_excel(writer, sheet_name="Seq Requests", index=False)

    bytes_io.seek(0)

    return Response(
        bytes_io, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=project_{project.identifier or f'P_{project.id}'}_export.xlsx"
        }
    )