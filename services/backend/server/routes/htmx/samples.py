from sqlalchemy import orm
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from opengsync_db import models, SyncSession, queries as Q, categories as C

from opengsync_db.core.blueprints import pd_transforms as T

from ...core import dependencies, exceptions as exc, responses, query_options
from ...components.tables import (
    Table, TableState, Col, Field, Text, Exact, Enum, Entity, Variant, related, TextColumn, StaticSpreadsheet,
)
from ... import forms


router = APIRouter(prefix="/samples", tags=["samples"])


S = models.Sample
_FULL_NAME = Q.search.full_name(models.User)
_LIBRARY_PATH = (S.library_links, models.links.SampleLibraryLink.library)


class SampleTable(Table):
    key = "smp"
    model = models.Sample
    noun = "samples"
    load = (
        orm.selectinload(S.library_links).selectinload(models.links.SampleLibraryLink.library),
        orm.selectinload(S.owner),
        orm.selectinload(S.project),
        orm.with_expression(S._num_libraries, S.num_libraries.expression),
    )
    columns = [
        Col("id", "ID", sort=True, search=Exact(S.id), hideable=False, size=1),
        Col("name", "Name", sort=True, search=Text(S.name, compact=True), hideable=False, size=3),
        Col(
            "project", "Project", size=2,
            sort=related(S.project, models.Project.title),
            search=Text(models.Project.title, models.Project.identifier, via=S.project),
            filter=Entity(
                models.Project, via=S.project, option=query_options.project_option,
                search=(models.Project.title, models.Project.identifier),
            ),
        ),
        Col("status", "Status", sort=True, filter=Enum(C.SampleStatus, nullable=True), size=2),
        Col(
            "owner", "Owner", size=1,
            sort=related(S.owner, _FULL_NAME),
            search=Text(_FULL_NAME, models.User.email, via=S.owner, weight=0.9),
            filter=Entity(models.User, via=S.owner, option=query_options.user_option, search=(_FULL_NAME, models.User.email)),
        ),
        Col("num_libraries", "# Libraries", sort=True, size=1),
        Col("library_types", "Library Types", size=4, filter=Enum(C.LibraryType, column=models.Library.type, via=_LIBRARY_PATH)),
        Col("qubit_concentration", "Qubit Conc.", sort=True, size=2),
        Col("avg_fragment_size", "Avg. Fragment Size", sort=True, size=2),
        Field(
            "seq_request", "Request",
            search=Text(models.SeqRequest.name, via=S.seq_requests),
            filter=Entity(
                models.SeqRequest, via=S.seq_requests, option=query_options.seq_request_option,
                search=(models.SeqRequest.name,),
            ),
        ),
        Field(
            "group", "Group",
            search=Text(models.Group.name, via=(S.project, models.Project.group)),
            filter=Entity(
                models.Group, via=(S.project, models.Project.group), option=query_options.group_option,
                search=(models.Group.name,),
            ),
        ),
    ]
    _browse = dict(row_template="components/tables/rows/browse-sample.html", dom_id="select-samples-table", url_state=False)
    variants = {
        "default": Variant(
            ["id", "name", "status", "owner", "num_libraries"], "components/tables/rows/sample.html", dom_id="sample-table",
        ),
        "library": Variant(
            ["id", "name", "status", "owner"], "components/tables/rows/library-sample.html",
            dom_id="library-sample-table", actions=True,
        ),
        "project": Variant(
            ["id", "name", "library_types", "status", "owner", "num_libraries"], "components/tables/rows/project-sample.html",
            dom_id="project-sample-table",
        ),
        "seq_request": Variant(
            ["id", "name", "project", "library_types"], "components/tables/rows/seq_request-sample.html",
            dom_id="seq_request-sample-table", actions=True,
        ),
        "seq_request-raw": Variant(
            ["id", "name", "status", "project", "library_types"], "components/tables/rows/seq_request-sample.html",
            dom_id="seq_request-sample-table", actions=True,
        ),
        "lab_prep": Variant(
            ["id", "name", "status", "owner", "num_libraries"], "components/tables/rows/lab_prep-sample.html",
            dom_id="lab_prep-sample-table",
        ),
        "browse": Variant(["id", "name", "status"], **_browse),
        "browse-qubit-measure": Variant(["id", "name", "status", "qubit_concentration"], **_browse),
        "browse-ba-report": Variant(["id", "name", "status", "avg_fragment_size"], **_browse),
    }


@router.get("/render-table-page")
def render_sample_table(
    library_id: int | None = Query(None, description="Optional library ID to filter samples"),
    lab_prep_id: int | None = Query(None, description="Optional lab prep ID to filter samples"),
    project_id: int | None = Query(None, description="Optional project ID to filter samples"),
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter samples"),
    browse: str | None = Query(None, description="Optional browse context to filter samples"),
    state: TableState = Depends(SampleTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.sample.select(
        library_id=library_id,
        lab_prep_id=lab_prep_id,
        project_id=project_id,
        seq_request_id=seq_request_id,
    )
    table = SampleTable(state, route="render_sample_table", user=current_user)

    if library_id is not None:
        if (access_level := session.get_access_level(Q.library.permissions(library_id, current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view samples for this library.")
        table.use("library", library_id=library_id, library=session.get_one(Q.library.select(id=library_id)))
        table.context["access_level"] = access_level
    elif project_id is not None:
        if session.get_access_level(Q.project.permissions(project_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view samples for this project.")
        table.use("project", project_id=project_id, project=session.get_one(Q.project.select(id=project_id)))
    elif seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view samples for this seq request.")
        seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
        variant = "seq_request-raw" if seq_request.submission_type == C.SubmissionType.RAW_SAMPLES else "seq_request"
        table.use(variant, seq_request_id=seq_request_id, seq_request=seq_request)
    elif lab_prep_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view samples for this lab prep.")
        table.use("lab_prep", lab_prep_id=lab_prep_id, lab_prep=session.get_one(Q.lab_prep.select(id=lab_prep_id)))
    elif not current_user.is_insider:
        stmt = Q.sample.select(viewer_id=current_user.id, statement=stmt)

    if browse is not None:
        table.use(f"browse-{browse}" if f"browse-{browse}" in SampleTable.variants else "browse", browse=browse)
        table.context["browse_context"] = browse

    return table.render(session, stmt)


@router.get("/sample-attribute-spreadsheet")
def render_sample_attribute_spreadsheet(
    seq_request_id: int = Query(..., description="Optional seq request ID to filter samples"),
    current_user_id: int = Depends(dependencies.require_user_id),
    session: SyncSession = Depends(dependencies.db_session),
):

    if seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user_id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        df = T.seq_request_sample_table(
            session.get_pandas(Q.pd.seq_request_sample_table(seq_request_id).order_by(models.Sample.id), limit=None)
        )
    else:
        raise exc.BadRequestException("seq_request_id must be provided.")

    df["project"] = df["project_identifier"]
    df.loc[df["project"].isna(), "project"] = df.loc[df["project"].isna(), "project_title"]
    df = df.drop(columns=["project_identifier", "project_title", "sample_id"])

    columns: list = [
        TextColumn("sample_name", "Sample Name", width=300),
    ]

    for column in df.columns:
        if column not in {"sample_name", "project"}:
            columns.append(TextColumn(column, column.replace("_", " ").title(), width=200))

    spreadsheet = StaticSpreadsheet(df, columns=columns, )

    return responses.htmx_response(content=spreadsheet.render())


@router.get("/query")
def query_samples(
    project_id: int = Query(..., description="Project of the samples"),
    word: str | None = Query(None, description="Search word for sample name"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user_id: int = Depends(dependencies.require_user_id),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    """Options for a spreadsheet QueryColumn: the samples of a project that can be reused, i.e. are not rejected."""
    if session.get_access_level(Q.project.permissions(project_id, current_user_id)) < C.AccessLevel.READ:
        raise exc.NoPermissionsException("You do not have permission to view samples for this project.")

    stmt = Q.sample.select(project_id=project_id).where(models.Sample.status.is_distinct_from(C.SampleStatus.REJECTED))
    return query_options.options_response(
        session, stmt, columns=query_options.SAMPLE_SEARCH_COLUMNS,
        word=word, page=page, order_column=models.Sample.name, label=lambda sample: sample.name,
    )


router.include_router(
    forms.models.SampleForm.Router(),
    dependencies=[Depends(dependencies.sample_permissions)],
)


@router.delete("/{sample_id}/delete")
def delete_sample(
    sample_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.sample_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException("You do not have permission to delete this sample.")

    sample = session.get_one(Q.sample.select(id=sample_id))
    session.delete(sample)

    return responses.htmx_response(
        redirect=responses.url_for("samples_page"),
        flash=responses.flash(f"Sample {sample.name} deleted.", "success")
    )