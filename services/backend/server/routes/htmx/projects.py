import io
import mimetypes
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel
from sqlalchemy import orm
from fastapi import APIRouter, Depends, Query

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from opengsync_db.core.blueprints import pd_transforms as T

from ...core import config, dependencies, responses, exceptions as exc, redis as rds
from ...components.tables import HTMXTable, TableCol
from ...core.context import ctx
from ...utils import parsing
from ...utils.file_browser import PROJECT_SERVABLE_EXTENSIONS, is_servable
from ...utils.io import is_browser_friendly
from ...utils.shared_file_browser import SharedFileBrowser
from ... import forms


router = APIRouter(prefix="/projects", tags=["projects"])
PROJECT_BROWSER_PAGE_LIMIT = 50


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
            sort_by="status",
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
        if (session.get_access_level(Q.user.permissions(user_id, current_user.id)) < C.AccessLevel.READ):
            raise exc.NoPermissionsException("You do not have permission to view projects for this user.")
        table.template = "components/tables/user-project.html"
        table.url_params["user_id"] = user_id
        table.context["user_id"] = user_id
    elif experiment_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view projects for this experiment.")
        table.template = "components/tables/experiment-project.html"
        table.url_params["experiment_id"] = experiment_id
        table.context["experiment_id"] = experiment_id
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
        from loguru import logger
        logger.debug(current_user)

    projects = table.paginate(
        session,
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
                models.Project._library_types,
                models.Project.library_types.expression  # pyright: ignore[reportAttributeAccessIssue]
            ),
        ],
    )
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

    projects, _ = session.page(stmt, page=page)
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
        }  # type: ignore
    ).T

    samples_df = T.project_samples(
        session.get_pandas(Q.pd.project_samples(project.id, with_libraries=False), limit=None),
        pivot=True,
    )
    libraries = session.get_pandas(Q.pd.project_data(project.id), limit=None)
    experiment_ids = libraries["experiment_id"].unique().tolist()
    library_ids = libraries["library_id"].unique().tolist()
    lanes = session.get_pandas(
        Q.pd.project_libraries_lanes(experiment_ids, library_ids),
        limit=None,
    )
    libraries_df = T.project_libraries(libraries, lanes, collapse_lanes_=True)
    seq_requests_df = T.project_seq_requests(
        session.get_pandas(Q.pd.project_seq_requests(project.id), limit=None)
    )
    library_properties_df = T.library_properties(
        session.get_pandas(Q.pd.library_properties(project_id=project.id), limit=None),
        expand_properties=True,
    )

    software = pd.DataFrame.from_records(
        {name: [data] for name, data in (project.software or {}).items()}  # type: ignore
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
    return responses.bytes_response(data=bytes_io.getvalue(), filename=f"project_{project.identifier or f'P_{project.id}'}.xlsx", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

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
        T.project_samples(
            session.get_pandas(Q.pd.project_samples(project_id), limit=None),
            pivot=True,
        )
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


@router.get("/{project_id}/overview", dependencies=[Depends(dependencies.project_permissions)])
def render_project_overview(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    libraries = session.get_pandas(Q.pd.project_data(project_id), limit=None)
    experiment_ids = libraries["experiment_id"].unique().tolist()
    library_ids = libraries["library_id"].unique().tolist()
    lanes = session.get_pandas(
        Q.pd.project_libraries_lanes(experiment_ids, library_ids),
        limit=None,
    )
    df = T.project_libraries(libraries, lanes, collapse_lanes_=True)

    LINK_WIDTH_UNIT = 1

    nodes = []
    links = []
    library_in_nodes = {}
    library_out_nodes = {}

    experiment_nodes = {}
    seq_request_nodes = {}
    idx = 0

    class ExperimentNameKey(BaseModel):
        experiment_name: str

    class SeqRequestIdKey(BaseModel):
        seq_request_id: int

    class SampleNameKey(BaseModel):
        sample_name: str

    class OverviewLibraryRow(BaseModel):
        library_name: str
        library_id: int
        seq_request_id: int
        experiment_name: str | None = None

    for key, _ in parsing.safe_groupby(df, ExperimentNameKey, dropna=True):
        node = {
            "node": idx,
            "name": key.experiment_name,
        }
        experiment_nodes[key.experiment_name] = node
        nodes.append(node)
        idx += 1

    for key, _ in parsing.safe_groupby(df, SeqRequestIdKey):
        node = {
            "node": idx,
            "name": f"Request {key.seq_request_id}",
        }
        seq_request_nodes[key.seq_request_id] = node
        nodes.append(node)
        idx += 1

    for key, sample_df in parsing.safe_groupby(df, SampleNameKey):
        sample_node = {
            "node": idx,
            "name": key.sample_name,
        }
        idx += 1
        nodes.append(sample_node)

        for _, row in parsing.safe_iter(sample_df, OverviewLibraryRow):
            library_name = row.library_name
            library_id = row.library_id
            seq_request_id = row.seq_request_id
            experiment_name = row.experiment_name

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

            if experiment_name is not None and library_id not in library_out_nodes:
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


@router.get("/render-feed")
def render_project_feed(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    PAGE_LIMIT = 10
    status_in = None
    user_id = None
    if current_user.is_insider:
        status_in = [C.ProjectStatus.PROCESSING, C.ProjectStatus.SEQUENCED]
    else:
        user_id = current_user.id

    projects, _ = session.page(
        Q.project.select(user_id=user_id, status_in=status_in).order_by(
            models.Project.status.desc(), models.Project.id.desc()
        ),
        page=page,
        limit=PAGE_LIMIT,
        options=[
            orm.selectinload(models.Project.assignees),
            orm.selectinload(models.Project.owner),
            orm.selectinload(models.Project.group),
            orm.with_expression(
                models.Project._num_samples, models.Project.num_samples.expression
            ),
            orm.with_expression(
                models.Project._library_status_counts, models.Project.library_status_counts.expression
            )
        ],
    )
    return responses.htmx_response(
        template="components/dashboard/projects-feed.html",
        projects=projects,
        current_page=page,
        limit=PAGE_LIMIT,
    )

@router.post("/{project_id}/add-assignee", dependencies=[Depends(dependencies.require_insider)])
def add_project_assignee(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    project = session.get_one(
        Q.project.select(id=project_id),
        options=[orm.selectinload(models.Project.assignees)],
    )

    if current_user in project.assignees:
        raise exc.BadRequestException("User is already an assignee.")

    project.assignees.append(current_user)
    return responses.htmx_response(flash=responses.flash("Assignee Added!", "success"))


@router.delete("/{project_id}/remove-assignee/{assignee_id}", dependencies=[Depends(dependencies.require_insider)])
def remove_project_assignee(
    project_id: int,
    assignee_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    project = session.get_one(
        Q.project.select(id=project_id),
        options=[orm.selectinload(models.Project.assignees)],
    )
    assignee = session.get_one(Q.user.select(id=assignee_id))
    if assignee not in project.assignees:
        raise exc.BadRequestException("Assignee not found in project.")

    project.assignees.remove(assignee)
    session.save(project)
    return responses.htmx_response(flash=responses.flash("Assignee removed.", "success"))

@router.delete("/{project_id}/remove-data_path", dependencies=[Depends(dependencies.require_insider)])
def remove_project_data_path(
    project_id: int,
    data_path_id: int = Query(..., description="Data path ID to remove"),
    session: SyncSession = Depends(dependencies.db_session),
):
    project = session.get_one(Q.project.select(id=project_id))
    data_path = session.get_one(Q.data_path.select(id=data_path_id))
    if data_path.project_id != project.id:
        raise exc.BadRequestException("Data path not found in project.")

    session.delete(data_path)

    return responses.htmx_response(
        redirect=ctx.request.url_for("project_page", project_id=project.id).include_query_params(tab="project-data_paths-tab"),
        flash=responses.flash("Data path removed.", "success"),
    )


def _subpath(subpath: str) -> Path:
    if not subpath or subpath in (".", "/"):
        return Path()
    return Path(subpath)


def _project_browser(project_id: int, session: SyncSession, redis: rds.RedisClient) -> tuple[SharedFileBrowser, list[models.DataPath]]:
    data_paths = list(session.get_all(Q.data_path.select(project_id=project_id), limit=None))
    browser = SharedFileBrowser.for_project(
        Path(config.settings.app_config.share_root),
        project_id,
        [data_path.path for data_path in data_paths],
        redis=redis,
    )
    return browser, data_paths


@router.get("/{project_id}/browse", name="project_browser_entries")
@router.get("/{project_id}/browse/{subpath:path}", name="project_browser_entries")
def project_browser_entries(
    project_id: int,
    subpath: str = "",
    page: int = Query(0, ge=0),
    sort_by: Literal["name", "size", "mtime"] = Query("name"),
    sort_order: Literal["asc", "desc"] | None = Query(None),
    _: C.AccessLevel = Depends(dependencies.project_permissions),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
    redis: rds.RedisClient = Depends(dependencies.redis),
):
    """Browse the project's data paths. The top level lists the data paths themselves."""
    if sort_order is None:
        sort_order = "asc" if sort_by == "name" else "desc"

    current_path = _subpath(subpath)
    browser, data_paths = _project_browser(project_id, session, redis)

    limit: int | None = PROJECT_BROWSER_PAGE_LIMIT
    if is_root_listing := not current_path.parts:
        limit = None
        paths = browser.list_roots(sort_by=sort_by, sort_order=sort_order)
    else:
        paths = browser.list_contents(
            current_path,
            limit=limit,
            offset=page * PROJECT_BROWSER_PAGE_LIMIT,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    # mark the entries that are data paths themselves (usually the top level, but nested ones too),
    # which are highlighted and the only ones insiders can remove
    by_path: dict[str, list[models.DataPath]] = {}
    for data_path in data_paths:
        by_path.setdefault(Path(data_path.path).as_posix(), []).append(data_path)
    for browser_path in paths:
        browser_path.data_paths = by_path.get(browser_path.rel_path.as_posix(), [])

    return responses.htmx_response(
        template="components/file-browser/entries.html",
        paths=paths,
        current_path=current_path,
        limit=limit,
        current_page=page,
        sort_by=sort_by,
        sort_order=sort_order,
        share_token=None,
        entries_route="project_browser_entries",
        route_params={"project_id": project_id},
        file_route="serve_project_file",
        servable_extensions=PROJECT_SERVABLE_EXTENSIONS,
        highlight_data_paths=True,
        remove_from_project_id=project_id if current_user.is_insider else None,
        is_root_listing=is_root_listing,
    )


@router.get("/{project_id}/files/{subpath:path}", name="serve_project_file")
def serve_project_file(
    project_id: int,
    subpath: str,
    _: C.AccessLevel = Depends(dependencies.project_permissions),
    session: SyncSession = Depends(dependencies.db_session),
    redis: rds.RedisClient = Depends(dependencies.redis),
):
    """Serve a file under the project's data paths. The URL mirrors the share root, so relative links in HTML reports resolve."""
    browser, _data_paths = _project_browser(project_id, session, redis)
    if (path := browser.get_file(_subpath(subpath))) is None:
        raise exc.NotFoundException("File not found.")
    if not is_servable(path):
        raise exc.NoPermissionsException("This file can only be downloaded through a data share link.")

    mimetype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return responses.file_response(
        path=path,
        filename=path.name,
        content_type=mimetype,
        disposition="inline" if is_browser_friendly(mimetype) else "attachment",
        require_accel=True,
    )


router.include_router(forms.models.ProjectForm.Router())
router.include_router(forms.actions.AddProjectAssigneeAction.Router())
router.include_router(forms.actions.SampleAttributeTableAction.Router())
router.include_router(forms.actions.MergeProjectsAction.Router())
router.include_router(forms.actions.ShareProjectDataAction.Router())
