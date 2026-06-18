from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import orm
import pandas as pd

from opengsync_db import models, AsyncSession, queries as Q, categories as C, actions, utils

from ...core import dependencies, responses, exceptions as exc
from ...forms.models import SeqRequestForm
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/seq_requests", tags=["seq_requests"])


class SeqRequestTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=4, searchable=True, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=3, choices=C.LibraryType.as_selectable()),
        TableCol(title="Status", label="status", col_size=1, sortable=True, sort_by="status_id", choices=C.SeqRequestStatus.as_selectable()),
        TableCol(title="Submission Type", label="submission_type", col_size=1, choices=C.SubmissionType.as_selectable()),
        TableCol(title="Group", label="group", col_size=2, searchable=True),
        TableCol(title="Requestor", label="requestor", col_size=2, searchable=True),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
        TableCol(title="Submitted", label="timestamp_submitted", col_size=2, sortable=True, sort_by="timestamp_submitted_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]


@router.get("/render-table-page")
async def render_seq_request_table(
    user_id: int | None = Query(None, description="Optional user ID to filter seq requests"),
    group_id: int | None = Query(None, description="Optional group ID to filter seq requests"),
    project_id: int | None = Query(None, description="Optional project ID to filter seq requests"),
    status_in: list[C.SeqRequestStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.SeqRequestStatus, query_param="status_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.SeqRequest, default=models.SeqRequest.timestamp_submitted_utc.desc())),
    session: AsyncSession = Depends(dependencies.db_session),
):
    table = SeqRequestTable(route="render_seq_request_table", page=page, order_by=order_by)

    if status_in:
        table.filter_values["status"] = status_in
    
    stmt = Q.seq_request.select(
        requestor_id=user_id,
        group_id=group_id,
        project_id=project_id,
        status_in=status_in,
    )

    if user_id is not None:
        if await session.get_access_level(Q.user.permissions(user_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view seq requests for this user.")
        template = "components/tables/user-seq_request.html"
    elif group_id is not None:
        if await session.get_access_level(Q.group.permissions(group_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view seq requests for this group.")
        template = "components/tables/group-seq_request.html"
    elif project_id is not None:
        if await session.get_access_level(Q.project.permissions(project_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view seq requests for this project.")
        template = "components/tables/project-seq_request.html"
    else:
        if not current_user.is_insider():
            stmt = Q.seq_request.select(viewer_id=current_user.id, statement=stmt)

        template = "components/tables/seq_request.html"

    seq_requests, count = await session.page(
        stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.SeqRequest.assignees),
            orm.with_expression(models.SeqRequest._library_types, models.SeqRequest.library_types.expression),
            orm.with_expression(models.SeqRequest._mux_types, models.SeqRequest.mux_types.expression),
            orm.selectinload(models.SeqRequest.requestor),
            orm.selectinload(models.SeqRequest.group),
        ]
    )
    table.set_num_pages(count)
    return await responses.htmx_response(template=template, seq_requests=seq_requests, table=table)

@router.get("/recent")
async def recent_seq_requests(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    session: AsyncSession = Depends(dependencies.db_session)
):
    options = [
        orm.selectinload(models.SeqRequest.assignees),
        orm.selectinload(models.SeqRequest.requestor),
        orm.with_expression(models.SeqRequest._num_libraries, models.SeqRequest.num_libraries.expression),
    ]
    if current_user.is_insider():        
        query = Q.seq_request.select(
            status_in=[
                C.SeqRequestStatus.SUBMITTED, C.SeqRequestStatus.ACCEPTED,
                C.SeqRequestStatus.SAMPLES_RECEIVED, C.SeqRequestStatus.PREPARED,
                C.SeqRequestStatus.DATA_PROCESSING
            ]
        ).order_by(
            models.SeqRequest.status_id,
            models.SeqRequest.timestamp_submitted_utc.desc()
        )
        
    else:
        query = Q.seq_request.select(
            status_in=[
                C.SeqRequestStatus.SUBMITTED, C.SeqRequestStatus.ACCEPTED,
                C.SeqRequestStatus.SAMPLES_RECEIVED, C.SeqRequestStatus.PREPARED,
                C.SeqRequestStatus.DATA_PROCESSING
            ],
            requestor_id=current_user.id
        ).order_by(
            models.SeqRequest.status_id,
            models.SeqRequest.timestamp_submitted_utc.desc()
        )

    seq_requests, num_total = await session.page(query, limit=10, page=page, options=options)

    return await responses.htmx_response("components/dashboard/seq_requests-list.html", seq_requests=seq_requests, num_total=num_total, current_page=page, limit=10)


@router.get("/create")
async def render_create_seq_request_form(
    request: Request,
    current_user: models.User = Depends(dependencies.require_user),
):
    """Render the create SeqRequest form."""
    form = SeqRequestForm(request, form_type="create")
    return await form.make_response()


@router.post("/create")
async def create_seq_request(response = Depends(SeqRequestForm.create)): return response


@router.get("/edit/{seq_request_id}")
async def render_edit_seq_request(
    seq_request_id: int,
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
    current_user: models.User = Depends(dependencies.require_user),
):
    """Render the edit SeqRequest form."""
    if access_level < C.AccessLevel.WRITE:
        return await responses.htmx_response(redirect=responses.url_for("seq_requests_page"))

    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))

    if seq_request.status_id != C.SeqRequestStatus.DRAFT.id and access_level < C.AccessLevel.INSIDER:
        return await responses.htmx_response(
            redirect=responses.url_for("seq_request_page", seq_request_id=seq_request_id)
        )

    form = SeqRequestForm(request, form_type="edit", seq_request=seq_request)
    return await form.make_response()


@router.post("/edit/{seq_request_id}")
async def edit_seq_request(response = Depends(SeqRequestForm.edit)): return response


@router.delete("/delete/{seq_request_id}")
async def delete_seq_request(
    seq_request_id: int,
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))

    if seq_request.status_id != C.SeqRequestStatus.DRAFT.id and access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException("Only draft requests can be deleted by non-admins.")

    await session.delete(seq_request)

    return await responses.htmx_response(
        redirect=request.url_for("seq_requests_page"),
        flash=responses.flash(f"Deleted sequencing request '{seq_request.name}'", "success"),
    )


@router.post("/archive/{seq_request_id}")
async def archive_seq_request(
    seq_request_id: int,
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))

    if seq_request.status_id != C.SeqRequestStatus.DRAFT.id and access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException()

    seq_request.status_id = C.SeqRequestStatus.ARCHIVED.id
    await session.save(seq_request)

    return await responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
        flash=responses.flash(f"Archived sequencing request '{seq_request.name}'", "success"),
    )


@router.post("/unarchive/{seq_request_id}")
async def unarchive_seq_request(
    seq_request_id: int,
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))

    seq_request.status_id = C.SeqRequestStatus.DRAFT.id
    seq_request.timestamp_submitted_utc = None
    await session.save(seq_request)

    return await responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
        flash=responses.flash(f"Unarchived sequencing request '{seq_request.name}'", "success"),
    )


@router.get("/export/{seq_request_id}")
async def export_seq_request(
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))

    metadata = {
        "Name": [seq_request.name],
        "Description": [seq_request.description or ""],
        "Requestor": [seq_request.requestor.name],
        "Requestor Email": [seq_request.requestor.email],
        "Submission Type": [seq_request.submission_type.name],
        "Organization": [seq_request.organization_contact.name],
        "Organization Address": [seq_request.organization_contact.address or ""],
        "Contact Person": [seq_request.contact_person.name],
        "Contact Person Email": [seq_request.contact_person.email],
        "Contact Person Phone": [seq_request.contact_person.phone or ""],
    }

    if seq_request.group is not None:
        metadata["Group"] = [seq_request.group.name]
        metadata["Group ID"] = [seq_request.group.id]

    if seq_request.billing_code is not None:
        metadata["Billing Code"] = [seq_request.billing_code]

    metadata_df = pd.DataFrame.from_records(metadata).T

    libraries_df = await session.pd.get_seq_request_libraries(seq_request_id, include_indices=True)
    features_df = await session.pd.get_seq_request_features(seq_request_id)

    bytes_io = BytesIO()
    with pd.ExcelWriter(bytes_io, engine="openpyxl") as writer:
        metadata_df.to_excel(writer, sheet_name="metadata", index=True)
        libraries_df.to_excel(writer, sheet_name="libraries", index=False)
        features_df.to_excel(writer, sheet_name="features", index=False)
    bytes_io.seek(0)

    return Response(
        bytes_io,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=request_{seq_request_id}.xlsx"},
    )


@router.get("/export-libraries/{seq_request_id}")
async def export_seq_request_libraries(
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))
    libraries_df = await session.pd.get_seq_request_libraries(seq_request_id, include_indices=True)

    return Response(
        libraries_df.to_csv(sep="\t", index=False).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=libraries_{seq_request.id}.tsv"},
    )


@router.post("/clone/{seq_request_id}")
async def clone_seq_request(
    seq_request_id: int,
    request: Request,
    method: Literal["pooled", "indexed", "raw"] = Query(...),
    session: AsyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))
    cloned_request = actions.clone_seq_request(session=session.sync_session, seq_request=seq_request, method=method)

    return await responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=cloned_request.id),
        flash=responses.flash("Request cloned", "success"),
    )


@router.delete("/remove-all-libraries/{seq_request_id}")
async def remove_all_seq_request_libraries(
    seq_request_id: int,
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))

    if seq_request.status_id != C.SeqRequestStatus.DRAFT.id and access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException()

    for library in seq_request.libraries:
        await session.delete(library)

    return await responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request_id),
        flash=responses.flash(f"Removed all libraries from sequencing request '{seq_request.name}'", "success"),
    )


@router.get("/overview/{seq_request_id}")
async def get_seq_request_overview(
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.samples)],
    )

    LINK_WIDTH_UNIT = 1
    samples = seq_request.samples

    nodes = []
    links = []
    contains_pooled = seq_request.submission_type == C.SubmissionType.POOLED_LIBRARIES

    idx = 0
    project_nodes: dict[int, int] = {}
    sample_nodes: dict[int, int] = {}
    library_nodes: dict[int, int] = {}
    pool_nodes: dict[int, int] = {}
    pool_link_widths: dict[int, int] = {}

    for sample in samples:
        if sample.project_id not in project_nodes:
            project_node = {"node": idx, "name": sample.project.title, "id": f"project-{sample.project_id}"}
            nodes.append(project_node)
            project_nodes[sample.project.id] = idx
            project_idx = idx
            idx += 1
        else:
            project_idx = project_nodes[sample.project.id]

        sample_node = {"node": idx, "name": sample.name, "id": f"sample-{sample.id}"}
        nodes.append(sample_node)
        sample_nodes[sample.id] = idx
        idx += 1

        n_sample_links = 0
        for link in sample.library_links:
            if link.library.seq_request_id == seq_request_id:
                n_sample_links += 1
                if link.library.id not in library_nodes:
                    library_node = {
                        "node": idx,
                        "name": link.library.type.identifier,
                        "id": f"library-{link.library.id}",
                    }
                    nodes.append(library_node)
                    library_nodes[link.library.id] = idx
                    library_idx = idx
                    idx += 1

                    if contains_pooled and link.library.pool is not None:
                        if link.library.pool_id not in pool_nodes:
                            pool_node = {
                                "node": idx,
                                "name": link.library.pool.name,
                                "id": f"pool-{link.library.pool.id}",
                            }
                            nodes.append(pool_node)
                            pool_nodes[link.library.pool.id] = idx
                            pool_link_widths[link.library.pool.id] = 0
                            pool_idx = idx
                            idx += 1
                        else:
                            pool_idx = pool_nodes[link.library.pool.id]

                        pool_link_widths[link.library.pool.id] += LINK_WIDTH_UNIT * link.library.num_samples
                        links.append({
                            "source": library_nodes[link.library.id],
                            "target": pool_idx,
                            "value": LINK_WIDTH_UNIT * link.library.num_samples,
                        })
                else:
                    library_idx = library_nodes[link.library.id]

                links.append({"source": sample_node["node"], "target": library_idx, "value": LINK_WIDTH_UNIT})

        links.append({
            "source": project_idx,
            "target": sample_nodes[sample.id],
            "value": LINK_WIDTH_UNIT * n_sample_links,
        })

    return await responses.htmx_response(
        "components/plots/request_overview.html",
        nodes=nodes, links=links, contains_pooled=contains_pooled,
    )


@router.get("/comments/{seq_request_id}")
async def get_seq_request_comments(
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.comments)],
    )

    return await responses.htmx_response("components/comment-list.html", comments=seq_request.comments)


@router.get("/files/{seq_request_id}")
async def get_seq_request_files(
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.media_files)],
    )

    return await responses.htmx_response(
        "components/file-list.html",
        files=seq_request.media_files,
        seq_request=seq_request,
        delete="delete_seq_request_file",
        delete_context={"seq_request_id": seq_request_id},
    )


@router.get("/assignees/{seq_request_id}")
async def get_seq_request_assignees(
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.assignees)],
    )

    return await responses.htmx_response(
        "components/tables/seq_request-assignee.html",
        assignees=seq_request.assignees,
        seq_request=seq_request,
    )


@router.delete("/assignees/{seq_request_id}/remove/{assignee_id}")
async def remove_seq_request_assignee(
    seq_request_id: int,
    assignee_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    seq_request = await session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.assignees)],
    )

    assignee = await session.get_one(Q.user.select(id=assignee_id))

    if assignee not in seq_request.assignees:
        raise exc.BadRequestException()

    seq_request.assignees.remove(assignee)
    await session.save(seq_request)

    return await responses.htmx_response(
        "components/tables/seq_request-assignee.html",
        assignees=seq_request.assignees,
        seq_request=seq_request,
    )


@router.get("/submit-checklist/{seq_request_id}")
async def get_seq_request_submit_checklist(
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))
    checklist = seq_request.get_submit_checklist()

    return await responses.htmx_response(
        "components/checklists/seq_request-submit.html",
        seq_request=seq_request, **checklist,
    )


@router.get("/review-checklist/{seq_request_id}")
async def get_seq_request_review_checklist(
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[
            orm.selectinload(models.SeqRequest.samples).selectinload(models.Sample.project),
            orm.selectinload(models.SeqRequest.libraries).selectinload(models.Library.pool),
            orm.selectinload(models.SeqRequest.sample_library_links).selectinload(models.links.SampleLibraryLink.library),
            orm.selectinload(models.SeqRequest.sample_library_links).selectinload(models.links.SampleLibraryLink.sample),
        ],
    )

    checklist = seq_request.get_review_checklist()
    contains_mux_samples = any(library.is_multiplexed() for library in seq_request.libraries)

    indices_checked = True
    for library in seq_request.libraries:
        for index in library.indices:
            if index.orientation is None or index.orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED:
                indices_checked = False
                break
        if not indices_checked:
            break

    return await responses.htmx_response(
        "components/checklists/seq_request-review.html",
        seq_request=seq_request,
        contains_mux_samples=contains_mux_samples,
        indices_checked=indices_checked,
        context=checklist,
    )


@router.post("/review-check/{seq_request_id}/{step}")
async def check_seq_request_review_step(
    seq_request_id: int,
    step: str,
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))

    if seq_request.review_checklist is None:
        seq_request.review_checklist = {}
    seq_request.review_checklist[step] = True
    await session.save(seq_request)

    return await responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id, tab="review-tab"),
    )


@router.post("/review-uncheck/{seq_request_id}/{step}")
async def uncheck_seq_request_review_step(
    seq_request_id: int,
    step: str,
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))

    if seq_request.review_checklist is None:
        seq_request.review_checklist = {}
    seq_request.review_checklist[step] = False
    await session.save(seq_request)

    return await responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id, tab="review-tab"),
    )


@router.get("/sample-table/{seq_request_id}")
async def get_seq_request_sample_table(
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))
    df = await session.pd.get_seq_request_sample_table(seq_request_id=seq_request_id)
    df["project"] = df["project_identifier"]
    df.loc[df["project"].isna(), "project"] = df.loc[df["project"].isna(), "project_title"]
    df = df.drop(columns=["project_identifier", "project_title", "sample_id"])

    from ...components.tables.spreadsheet import TextColumn
    from ...components.tables import StaticSpreadsheet

    columns: list = [TextColumn("sample_name", "Sample Name", width=300)]
    for column in df.columns:
        if column not in {"sample_name", "project"}:
            columns.append(TextColumn(column, column.replace("_", " ").title(), width=200))

    spreadsheet = StaticSpreadsheet(df, columns=columns)

    return await responses.htmx_response(
        "components/itable.html", seq_request=seq_request, spreadsheet=spreadsheet
    )


@router.post("/confirm-barcodes/{seq_request_id}")
async def confirm_seq_request_barcodes(
    seq_request_id: int,
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[
            orm.selectinload(models.SeqRequest.libraries).selectinload(models.Library.indices),
        ],
    )

    for library in seq_request.libraries:
        for index in library.indices:
            if index.orientation is None or index.orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED:
                index.orientation = C.BarcodeOrientation.FORWARD

    await session.save(seq_request)

    return await responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
    )


@router.delete("/remove-share-email/{seq_request_id}/{email}")
async def remove_seq_request_share_email(
    seq_request_id: int,
    email: str,
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    seq_request = await session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.delivery_email_links)],
    )

    if len(seq_request.delivery_email_links) == 1:
        raise exc.NoPermissionsException()

    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    share_email_link = await session.first(
        Q.links.get_seq_request_delivery_email_link(seq_request_id=seq_request_id, email=email)
    )
    if share_email_link is None:
        raise exc.ItemNotFoundException()

    await session.delete(share_email_link)

    return await responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id, tab="request-share-tab"),
        flash=responses.flash("Removed email!", "success"),
    )

@router.post("/add-assignee")
async def add_assignee_to_seq_request(
    seq_request_id: int = Query(...),
    assignee_id: int | None = Query(None),
    session: AsyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    """Add an assignee to a SeqRequest."""
    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))

    if assignee_id is not None:
        assignee = await session.get_one(Q.user.select(id=assignee_id))
    else:
        assignee = current_user

    if not assignee.is_insider():
        raise exc.NoPermissionsException("Assignee must be an insider.")

    if assignee in seq_request.assignees:
        raise exc.BadRequestException("User is already an assignee.")

    seq_request.assignees.append(assignee)
    await session.save(seq_request)

    return await responses.htmx_response(
        redirect=responses.url_for("dashboard"),
        flash=responses.flash("Assignee Added!", "success"),
    )