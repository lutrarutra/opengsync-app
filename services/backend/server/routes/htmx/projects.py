import io
import pandas as pd
from sqlalchemy import orm
from fastapi import APIRouter, Depends, Query, Request, Response

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol
from ...core.context import ctx
from ... import forms


router = APIRouter(prefix="/projects", tags=["projects"])

class ProjectTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(
            title="Identifier",
            label="identifier",
            col_size=1,
            searchable=True,
            sortable=True,
        ),
        TableCol(
            title="Title", label="title", col_size=3, searchable=True, sortable=True
        ),
        TableCol(
            title="Library Types",
            label="library_types",
            col_size=2,
            choices=C.LibraryType.as_selectable(),
        ),
        TableCol(
            title="Status",
            label="status",
            col_size=1,
            sort_by="status_id",
            sortable=True,
            choices=C.ProjectStatus.as_selectable(),
        ),
        TableCol(title="Group", label="group", col_size=2),
        TableCol(title="Owner", label="owner_name", col_size=2, searchable=True),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
    ]


@router.get("/render-table-page")
def render_project_table(
    user_id: int | None = Query(None, description="Optional User ID for whom to render the project table"),
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter projects"),
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter projects"),
    group_id: int | None = Query(None, description="Optional group ID to filter projects"),
    title: str | None = Query(None, description="Optional title to search for in project titles"),
    identifier: str | None = Query(None, description="Optional identifier to search for in project identifiers"),
    owner_name: str | None = Query(None, description="Optional owner name to search for in project owners"),
    status_in: list[C.ProjectStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.ProjectStatus, query_param="status_in")),
    library_types_in: list[C.LibraryType] | None = Depends(dependencies.parse_enum_ids(enum_type=C.LibraryType, query_param="library_types_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Project, default=models.Project.id.desc())),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = ProjectTable(route="render_project_table", page=page, order_by=order_by)

    if status_in:
        table.filter_values["status"] = status_in
    if library_types_in:
        table.filter_values["library_types"] = library_types_in

    stmt = Q.project.select(
        user_id=user_id,
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
        group_id=group_id,
        status_in=status_in,
        library_types_in=library_types_in,
    )

    if title:
        table.active_search_var = "title"
        table.active_query_value = title
    elif identifier:
        table.active_search_var = "identifier"
        table.active_query_value = identifier
    elif owner_name:
        table.active_search_var = "owner_name"
        table.active_query_value = owner_name

    stmt = Q.project.search(
        title=title,
        identifier=identifier,
        owner_name=owner_name,
        statement=stmt,
    )

    if user_id is not None:
        if (
            session.get_access_level(Q.user.permissions(user_id, current_user.id))
            < C.AccessLevel.READ
        ):
            raise exc.NoPermissionsException(
                "You do not have permission to view projects for this user."
            )
        table.template = "components/tables/user-project.html"
        table.url_params["user_id"] = user_id
    elif experiment_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view projects for this experiment.")
        table.template = "components/tables/experiment-project.html"
        table.url_params["experiment_id"] = experiment_id
    elif seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view projects for this seq request.")
        table.template = "components/tables/seq_request-project.html"
        table.url_params["seq_request_id"] = seq_request_id
        table.context["seq_request_id"] = seq_request_id
    elif group_id is not None:
        if session.get_access_level(Q.group.permissions(group_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view projects for this group.")
        table.template = "components/tables/group-project.html"
        table.url_params["group_id"] = group_id
        table.context["group_id"] = group_id
    else:
        table.template = "components/tables/project.html"
        if not current_user.is_insider:
            stmt = Q.project.select(viewer_id=current_user.id, statement=stmt)

    projects, count = session.page(
        stmt,
        page=page,
        order_by=order_by,
        options=[
            orm.selectinload(models.Project.assignees),
            orm.selectinload(models.Project.owner),
            orm.selectinload(models.Project.group),
            orm.with_expression(
                models.Project._num_samples, models.Project.num_samples.expression
            ),
            orm.with_expression(
                models.Project._library_types, models.Project.library_types.expression
            ),
        ],
    )
    table.set_num_pages(count)
    return table.make_response(projects=projects)

@router.get("/search")
def search_projects(
    word: str | None = Query(None, description="Search word for project title or identifier"),
    group_id: int | None = Query(None, description="Optional group ID to filter projects"),
    status_in: list[C.ProjectStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.ProjectStatus, query_param="status_in")),
    selected_id: int | None = Query(None, description="Currently selected project"),
    current_user: models.User = Depends(dependencies.require_user),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.project.select(group_id=group_id, status_in=status_in)

    if selected_id is not None and not word:
        stmt = Q.project.select(id=selected_id, statement=stmt)
    elif word is not None:
        stmt = Q.project.search(title=word, identifier=word, statement=stmt)

    if not current_user.is_insider:
        if group_id is not None:
            if session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id)) < C.AccessLevel.READ:
                raise exc.NoPermissionsException("You do not have permission to view this resource.")
        else:    
            stmt = Q.project.select(viewer_id=current_user.id, statement=stmt)

    projects, count = session.page(stmt, page=page)
    return responses.htmx_response(template="components/search/project.html", projects=projects)

@router.get("/{project_id}/export", dependencies=[Depends(dependencies.project_permissions)])
def export_project_data(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    project = session.get_one(
        Q.project.select(id=project_id).options(
            orm.selectinload(models.Project.libraries)
        )
    )

    metadata = pd.DataFrame.from_records(
        {
            "Project ID": [project.id],
            "Project Identifier": [project.identifier],
            "Project Title": [project.title],
            "Owner": [project.owner.name],
            "Created At": [project.timestamp_created.isoformat()],
            "Status": [project.status.name],
            "Group": [project.group.name if project.group else "N/A"],
            "Number of Samples": [project.num_samples],
        }
    ).T

    samples_df = session.pd.get_project_samples(project_id=project.id)
    libraries_df = session.pd.get_project_libraries(project_id=project.id)
    seq_requests_df = session.pd.get_project_seq_requests(project_id=project.id)
    library_properties_df = session.pd.get_library_properties(
        project_id=project.id
    )

    software = pd.DataFrame.from_records(
        {name: [data] for name, data in (project.software or {}).items()}
    ).T

    bytes_io = io.BytesIO()

    with pd.ExcelWriter(bytes_io, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="Metadata")
        samples_df.to_excel(writer, sheet_name="Samples", index=False)
        libraries_df.to_excel(writer, sheet_name="Libraries", index=False)
        seq_requests_df.to_excel(writer, sheet_name="Seq Requests", index=False)
        software.to_excel(writer, sheet_name="Software")
        library_properties_df.to_excel(
            writer, sheet_name="Library Properties", index=False
        )

    bytes_io.seek(0)
    return responses.bytes_response(bytes_io.getvalue(), filename=f"project_{project.identifier or f'P_{project.id}'}.xlsx", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.delete("/{project_id}/delete")
def delete_project(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.project_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException(
            "You do not have permission to delete this project."
        )

    project = session.get_one(
        Q.project.select(id=project_id).options(
            orm.with_expression(
                models.Project._num_samples, models.Project.num_samples.expression
            ),
        )
    )

    if (project.num_samples) > 0:
        return responses.htmx_response(
            redirect=ctx.request.url_for("project_page", project_id=project_id),
            flash=responses.flash(
                "Cannot delete project non empty project.", "warning"
            ),
        )

    session.delete(project, flush=True)

    return responses.htmx_response(
        redirect=ctx.request.url_for("projects_page"),
        flash=responses.flash(
            f"Project '{project.title}' has been deleted.", "success"
        ),
    )


@router.post("/{project_id}/complete", dependencies=[Depends(dependencies.require_insider)])
def complete_project(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    project = session.get_one(Q.project.select(id=project_id))

    for library in project.libraries:
        if library.status not in {
            C.LibraryStatus.SHARED,
            C.LibraryStatus.FAILED,
            C.LibraryStatus.REJECTED,
            C.LibraryStatus.ARCHIVED,
        }:
            return responses.htmx_response(
                redirect=ctx.request.url_for("project_page", project_id=project_id),
                flash=responses.flash(
                    f"Cannot complete project {project.title} because some libraries are not shared/failed/rejected/archived.",
                    "warning",
                ),
            )

    project.status = C.ProjectStatus.DELIVERED
    return responses.htmx_response(
        redirect=ctx.request.url_for("project_page", project_id=project.id),
        flash=responses.flash("Project Completed!", "success"),
    )


@router.get("/{project_id}/edit-sample-attributes")
def render_project_sample_attributes_form(
    access_level: C.AccessLevel = Depends(dependencies.project_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException(
            "You do not have permission to edit this project."
        )

    pass


@router.get(
    "/{project_id}/sample-attributes",
    dependencies=[Depends(dependencies.project_permissions)],
)
def render_project_sample_attribute_spreadsheet(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    from ...components.tables.spreadsheet import TextColumn
    from ...components.tables import StaticSpreadsheet

    df = (
        session.pd.get_project_samples(project_id=project_id)
        .sort_values("sample_id")
        .reset_index(drop=True)
        .rename(columns={"sample_id": "id", "sample_name": "name"})
    )

    columns = []
    for col in df.columns:
        if "id" == col:
            width = 50
        elif "name" == col:
            width = 300
        else:
            width = 150
        columns.append(
            TextColumn(col, col.replace("_", " ").title(), width, max_length=1000)
        )

    spreadsheet = StaticSpreadsheet(df, columns=columns, id="sample-attribute-table")
    return responses.htmx_response(content=spreadsheet.render())


@router.get(
    "/{project_id}/overview", dependencies=[Depends(dependencies.project_permissions)]
)
def render_project_overview(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):

    df = session.pd.get_project_libraries(project_id=project_id)

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

    for (seq_request_id,), _ in df.groupby(
        [
            "seq_request_id",
        ]
    ):
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
            experiment_name = (
                row["experiment_name"] if pd.notna(row["experiment_name"]) else None
            )

            if library_id not in library_in_nodes:
                library_in_node = {
                    "node": idx,
                    "name": library_name,
                }
                idx += 1
                nodes.append(library_in_node)
                library_in_nodes[library_id] = library_in_node
                links.append(
                    {
                        "source": library_in_node["node"],
                        "target": seq_request_nodes[seq_request_id]["node"],
                        "value": LINK_WIDTH_UNIT
                        * len(df[df["library_id"] == library_id]),
                    }
                )
            else:
                library_in_node = library_in_nodes[library_id]

            links.append(
                {
                    "source": sample_node["node"],
                    "target": library_in_node["node"],
                    "value": LINK_WIDTH_UNIT,
                }
            )

            if experiment_name is not None:
                if library_id not in library_out_nodes:
                    library_out_node = {
                        "node": idx,
                        "name": library_name,
                    }
                    idx += 1
                    nodes.append(library_out_node)
                    library_out_nodes[library_id] = library_out_node
                    links.append(
                        {
                            "source": library_out_node["node"],
                            "target": experiment_nodes[experiment_name]["node"],
                            "value": LINK_WIDTH_UNIT
                            * len(df[df["library_id"] == library_id]),
                        }
                    )
                    links.append(
                        {
                            "source": seq_request_nodes[seq_request_id]["node"],
                            "target": library_out_node["node"],
                            "value": LINK_WIDTH_UNIT
                            * len(
                                df[
                                    (df["library_id"] == library_id)
                                    & (df["seq_request_id"] == seq_request_id)
                                ]
                            ),
                        }
                    )

    return responses.htmx_response(
        template="components/plots/project_overview.html",
        nodes=nodes, links=links,
    )


@router.get("/{project_id}/assignee-form", dependencies=[Depends(dependencies.require_insider)])
def render_project_assignee_form(
    project_id: int,
):
    pass


@router.get("/{project_id}/software", dependencies=[Depends(dependencies.project_permissions)])
def render_project_software(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    project = session.get_one(Q.project.select(id=project_id))

    return responses.htmx_response(
        template="components/project-software.html",
        software=project.software or {},
        project=project,
    )

router.include_router(forms.models.ProjectForm.Router())
