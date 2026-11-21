import io

import pandas as pd
from sqlalchemy import orm
from fastapi import APIRouter, Depends, Query

from opengsync_db import models, SyncSession, queries as Q, categories as C

from opengsync_db.core.blueprints import pd_transforms as T
from opengsync_db.transitions import run_operation, release as release_ops

from ...core import dependencies, overview, responses, exceptions as exc, query_options
from ...utils.io import cells_as_text
from ...components.tables import Table, TableState, Col, Text, Exact, Enum, Entity, Variant, related
from ...core.context import ctx
from ... import forms
from .data_browser import DataScope, data_browser_router


router = APIRouter(prefix="/projects", tags=["projects"])


PR = models.Project
_FULL_NAME = Q.search.full_name(models.User)


class ProjectTable(Table):
    key = "prj"
    model = models.Project
    noun = "projects"
    load = (
        orm.selectinload(PR.assignees),
        orm.selectinload(PR.owner),
        orm.selectinload(PR.group),
        orm.with_expression(PR._num_samples, PR.num_samples.expression),
        orm.with_expression(PR._library_types, PR.library_types.expression),  # pyright: ignore[reportAttributeAccessIssue]
    )
    columns = [
        Col("id", "ID", sort=True, search=Exact(PR.id), hideable=False, size=1),
        Col("identifier", "Identifier", sort=True, search=Text(PR.identifier, compact=True), size=1),
        Col("title", "Title", sort=True, search=Text(PR.title, compact=True), hideable=False, size=3),
        Col(
            "library_types", "Library Types", size=2,
            filter=Enum(C.LibraryType, column=models.Library.type, via=(PR.samples, models.Sample.library_links, models.links.SampleLibraryLink.library)),
        ),
        Col("status", "Status", sort=True, filter=Enum(C.ProjectStatus), size=1),
        Col(
            "group", "Group", size=2,
            sort=related(PR.group, models.Group.name),
            search=Text(models.Group.name, via=PR.group),
            filter=Entity(models.Group, via=PR.group, option=query_options.group_option, search=(models.Group.name,)),
        ),
        Col(
            "owner_name", "Owner", size=2,
            sort=related(PR.owner, _FULL_NAME),
            search=Text(_FULL_NAME, models.User.email, via=PR.owner, weight=0.9),
            filter=Entity(models.User, via=PR.owner, option=query_options.user_option, search=(_FULL_NAME, models.User.email)),
        ),
        Col(
            "assignees", "Assignees", size=2, sort=PR.num_assignees,
            search=Text(_FULL_NAME, models.User.email, via=PR.assignees, weight=0.9),
            filter=Entity(
                models.User, via=PR.assignees, option=query_options.user_option,
                search=(_FULL_NAME, models.User.email), from_rows=True,
            ),
        ),
        Col("num_samples", "# Samples", sort=True, size=1),
    ]
    variants = {
        "default": Variant(
            ["id", "identifier", "title", "library_types", "status", "group", "owner_name", "num_samples", "assignees"],
            "components/tables/rows/project.html", dom_id="project-table",
        ),
        "user": Variant(
            ["id", "identifier", "title", "library_types", "status", "num_samples"],
            "components/tables/rows/user-project.html", dom_id="user-project-table",
        ),
        "experiment": Variant(
            ["id", "identifier", "title", "library_types", "status", "group", "owner_name", "num_samples", "assignees"],
            "components/tables/rows/experiment-project.html", dom_id="experiment-project-table",
        ),
        "seq_request": Variant(
            ["id", "identifier", "title", "status", "group", "owner_name", "num_samples"],
            "components/tables/rows/seq_request-project.html", dom_id="seq_request-project-table",
        ),
        "group": Variant(
            ["id", "identifier", "title", "status", "owner_name", "num_samples"],
            "components/tables/rows/group-project.html", dom_id="group-project-table",
        ),
    }


@router.get("/render-table-page")
def render_project_table(
    user_id: int | None = Query(None, description="Optional User ID for whom to render the project table"),
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter projects"),
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter projects"),
    group_id: int | None = Query(None, description="Optional group ID to filter projects"),
    state: TableState = Depends(ProjectTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.project.select(
        # user tab lists only owned projects (matches User.num_projects tab count)
        owner_id=user_id,
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
        group_id=group_id,
    )
    table = ProjectTable(state, route="render_project_table", user=current_user)

    if user_id is not None:
        if (session.get_access_level(Q.user.permissions(user_id, current_user.id)) < C.AccessLevel.READ):
            raise exc.NoPermissionsException("You do not have permission to view projects for this user.")
        table.use("user", user_id=user_id)
        table.context["user_id"] = user_id
    elif experiment_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view projects for this experiment.")
        table.use("experiment", experiment_id=experiment_id)
        table.context["experiment_id"] = experiment_id
    elif seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view projects for this seq request.")
        table.use("seq_request", seq_request_id=seq_request_id)
        table.context["seq_request_id"] = seq_request_id
    elif group_id is not None:
        if session.get_access_level(Q.group.permissions(group_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view projects for this group.")
        table.use("group", group_id=group_id)
        table.context["group_id"] = group_id
    elif not current_user.is_insider:
        stmt = Q.project.select(viewer_id=current_user.id, statement=stmt)

    return table.render(session, stmt)

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
    elif word:
        stmt = Q.project.search(title=word, identifier=word, statement=stmt)
    else:
        stmt = stmt.order_by(models.Project.title.asc())

    if not current_user.is_insider:
        if group_id is not None:
            if session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id)) < C.AccessLevel.READ:
                raise exc.NoPermissionsException("You do not have permission to view this resource.")
        else:    
            stmt = Q.project.select(viewer_id=current_user.id, statement=stmt)

    return query_options.search_response(session, stmt, page=page, option=query_options.project_option)

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
        cells_as_text(writer.book)

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

    with run_operation(session, release_ops.COMPLETE, subject=project):
        project.status = C.ProjectStatus.DELIVERED
    return responses.htmx_response(
        redirect=ctx.request.url_for("project_page", project_id=project.id),
        flash=responses.flash("Project Completed!", "success"),
    )


@router.post("/{project_id}/archive", dependencies=[Depends(dependencies.require_insider)])
def archive_project(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    """Archive the project. Only the project status changes; samples/libraries are untouched."""
    project = session.get_one(Q.project.select(id=project_id))

    with run_operation(session, release_ops.ARCHIVE, subject=project):
        project.status = C.ProjectStatus.ARCHIVED
        session.save(project)

    return responses.htmx_response(
        redirect=ctx.request.url_for("project_page", project_id=project.id),
        flash=responses.flash(f"Archived project '{project.title}'", "success"),
    )


@router.post("/{project_id}/unarchive", dependencies=[Depends(dependencies.require_insider)])
def unarchive_project(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    """Restore an archived project. The previous status is not stored, so it is derived
    from the libraries: none -> DRAFT, all finished -> DELIVERED, otherwise PROCESSING."""
    project = session.get_one(Q.project.select(id=project_id))

    if project.status != C.ProjectStatus.ARCHIVED:
        return responses.htmx_response(
            redirect=ctx.request.url_for("project_page", project_id=project_id),
            flash=responses.flash(f"Project '{project.title}' is not archived.", "warning"),
        )

    finished_statuses = {
        C.LibraryStatus.SHARED,
        C.LibraryStatus.FAILED,
        C.LibraryStatus.REJECTED,
        C.LibraryStatus.ARCHIVED,
    }
    with run_operation(session, release_ops.UNARCHIVE, subject=project):
        if not project.libraries:
            project.status = C.ProjectStatus.DRAFT
        elif all(library.status in finished_statuses for library in project.libraries):
            project.status = C.ProjectStatus.DELIVERED
        else:
            project.status = C.ProjectStatus.PROCESSING
        session.save(project)

    return responses.htmx_response(
        redirect=ctx.request.url_for("project_page", project_id=project.id),
        flash=responses.flash(f"Unarchived project '{project.title}'", "success"),
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
    current_user: models.User = Depends(dependencies.require_user),
) -> dict:
    """Samples → libraries → pools → experiments of the project (JSON for static/js/overview-graph.js)."""
    return overview.project_graph(session, project_id, insider=current_user.is_insider)

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

    projects, total = session.page(
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
            ),
            orm.with_expression(
                models.Project._library_types, models.Project.library_types.expression
            ),
        ],
    )
    return responses.htmx_response(
        template="components/dashboard/projects-feed.html",
        projects=projects,
        current_page=page,
        limit=PAGE_LIMIT,
        total=total,
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
    session.save(project)
    return responses.htmx_response(flash=responses.flash("Assignee Added!", "success"))


@router.get("/{project_id}/feed-assignees", dependencies=[Depends(dependencies.require_insider)])
def render_project_feed_assignees(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    """Re-render the dashboard feed assign/unassign controls after a (un)assign."""
    project = session.get_one(
        Q.project.select(id=project_id),
        options=[orm.selectinload(models.Project.assignees)],
    )
    return responses.htmx_response(template="components/dashboard/project-assignees.html", project=project)


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

router.include_router(data_browser_router(DataScope(
    entity="project", label="project", permissions=dependencies.project_permissions,
    page_route="project_page", tab="project-data_paths-tab",
)))
router.include_router(forms.models.ProjectForm.Router())
router.include_router(forms.actions.AddProjectAssigneeAction.Router())
router.include_router(forms.actions.SampleAttributeTableAction.Router())
router.include_router(forms.actions.MergeProjectsAction.Router())
router.include_router(forms.actions.ShareProjectDataAction.Router())
