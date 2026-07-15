import os
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import orm
import pandas as pd

from opengsync_db import (
    models,
    SyncSession,
    queries as Q,
    categories as C,
    actions,
    utils,
)

from ...core import dependencies, responses, exceptions as exc, config
from ... import forms
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/seq_requests", tags=["seq_requests"])
router.include_router(forms.models.SeqRequestForm.Router())
router.include_router(forms.actions.SubmitSeqRequestAction.Router())

class SeqRequestTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(
            title="Name", label="name", col_size=4, searchable=True, sortable=True
        ),
        TableCol(
            title="Library Types",
            label="library_types",
            col_size=3,
            choices=C.LibraryType.as_selectable(),
        ),
        TableCol(
            title="Status",
            label="status",
            col_size=1,
            sortable=True,
            sort_by="status_id",
            choices=C.SeqRequestStatus.as_selectable(),
        ),
        TableCol(
            title="Submission Type",
            label="submission_type",
            col_size=1,
            choices=C.SubmissionType.as_selectable(),
        ),
        TableCol(title="Group", label="group", col_size=2, searchable=True),
        TableCol(title="Requestor", label="requestor", col_size=2, searchable=True),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
        TableCol(
            title="Submitted",
            label="timestamp_submitted",
            col_size=2,
            sortable=True,
            sort_by="timestamp_submitted_utc",
        ),
        TableCol(
            title="Completed",
            label="timestamp_completed",
            col_size=2,
            sortable=True,
            sort_by="timestamp_finished_utc",
        ),
    ]


@router.get("/render-table-page")
def render_seq_request_table(
    user_id: int | None = Query(None, description="Optional user ID to filter seq requests"),
    group_id: int | None = Query(None, description="Optional group ID to filter seq requests"),
    project_id: int | None = Query(None, description="Optional project ID to filter seq requests"),
    name: str | None = Query(None, description="Optional name search term to filter seq requests"),
    group: str | None = Query(None, description="Optional group name search term to filter seq requests"),
    requestor: str | None = Query(None, description="Optional requestor name search term to filter seq requests"),
    status_in: list[C.SeqRequestStatus] | None = Depends(
        dependencies.parse_enum_ids(
            enum_type=C.SeqRequestStatus, query_param="status_in"
        )
    ),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    order_by: utils.OrderBy | None = Depends(
        dependencies.parse_order_by(
            model=models.SeqRequest,
            default=models.SeqRequest.timestamp_submitted_utc.desc(),
        )
    ),
    session: SyncSession = Depends(dependencies.db_session),
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

    if name:
        table.active_search_var = "name"
        table.active_query_value = name
    elif requestor:
        table.active_search_var = "requestor"
        table.active_query_value = requestor
    elif group:
        table.active_search_var = "group"
        table.active_query_value = group

    stmt = Q.seq_request.search(
        name=name,
        requestor_name=requestor,
        group_name=group,
        statement=stmt,
    )

    if user_id is not None:
        if session.get_access_level(Q.user.permissions(user_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view seq requests for this user.")
        table.template = "components/tables/user-seq_request.html"
        table.url_params["user_id"] = user_id
    elif group_id is not None:
        if session.get_access_level(Q.group.permissions(group_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view seq requests for this group.")
        table.template = "components/tables/group-seq_request.html"
        table.url_params["group_id"] = group_id
    elif project_id is not None:
        if session.get_access_level(Q.project.permissions(project_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view seq requests for this project.")
        table.template = "components/tables/project-seq_request.html"
        table.url_params["project_id"] = project_id
    else:
        if not current_user.is_insider:
            stmt = Q.seq_request.select(viewer_id=current_user.id, statement=stmt)

        table.template = "components/tables/seq_request.html"

    seq_requests, count = session.page(
        stmt,
        page=page,
        order_by=order_by,
        options=[
            orm.selectinload(models.SeqRequest.assignees),
            orm.with_expression(
                models.SeqRequest._library_types,
                models.SeqRequest.library_types.expression,
            ),
            orm.with_expression(
                models.SeqRequest._mux_types, models.SeqRequest.mux_types.expression
            ),
            orm.selectinload(models.SeqRequest.requestor),
            orm.selectinload(models.SeqRequest.group),
        ],
    )
    table.set_num_pages(count)
    return table.make_response(seq_requests=seq_requests)


@router.get("/recent")
def recent_seq_requests(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    options = [
        orm.selectinload(models.SeqRequest.assignees),
        orm.selectinload(models.SeqRequest.requestor),
        orm.with_expression(
            models.SeqRequest._num_libraries, models.SeqRequest.num_libraries.expression
        ),
    ]
    if current_user.is_insider:
        query = Q.seq_request.select(
            status_in=[
                C.SeqRequestStatus.SUBMITTED,
                C.SeqRequestStatus.ACCEPTED,
                C.SeqRequestStatus.SAMPLES_RECEIVED,
                C.SeqRequestStatus.PREPARED,
                C.SeqRequestStatus.DATA_PROCESSING,
            ]
        ).order_by(
            models.SeqRequest.status_id,
            models.SeqRequest.timestamp_submitted_utc.desc(),
        )

    else:
        query = Q.seq_request.select(
            status_in=[
                C.SeqRequestStatus.SUBMITTED,
                C.SeqRequestStatus.ACCEPTED,
                C.SeqRequestStatus.SAMPLES_RECEIVED,
                C.SeqRequestStatus.PREPARED,
                C.SeqRequestStatus.DATA_PROCESSING,
            ],
            requestor_id=current_user.id,
        ).order_by(
            models.SeqRequest.status_id,
            models.SeqRequest.timestamp_submitted_utc.desc(),
        )

    seq_requests, num_total = session.page(
        query, limit=10, page=page, options=options
    )

    return responses.htmx_response(
        "components/dashboard/seq_requests-list.html",
        seq_requests=seq_requests,
        num_total=num_total,
        current_page=page,
        limit=10,
    )


@router.get("/{seq_request_id}/process-request")
def render_process_seq_request_form(
    seq_request_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    """Render the process SeqRequest form."""
    if access_level < C.AccessLevel.WRITE:
        return responses.htmx_response(
            redirect=responses.url_for("seq_requests_page")
        )

    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id).options(
            orm.selectinload(models.SeqRequest.contact_person),
        )
    )

    if (
        seq_request.status_id != C.SeqRequestStatus.SUBMITTED.id
        and access_level < C.AccessLevel.INSIDER
    ):
        return responses.htmx_response(
            redirect=responses.url_for(
                "seq_request_page", seq_request_id=seq_request_id
            )
        )

    form = forms.actions.ProcessSeqRequestForm(request, seq_request=seq_request)
    return form.make_response()


@router.post("/{seq_request_id}/process-request")
def process_request(response=Depends(forms.actions.ProcessSeqRequestForm.process_request)): return response


@router.delete("/{seq_request_id}/delete")
def delete_seq_request(
    seq_request_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

    if (
        seq_request.status_id != C.SeqRequestStatus.DRAFT.id
        and access_level < C.AccessLevel.INSIDER
    ):
        raise exc.NoPermissionsException(
            "Only draft requests can be deleted by non-admins."
        )

    session.delete(seq_request)

    return responses.htmx_response(
        redirect=request.url_for("seq_requests_page"),
        flash=responses.flash(
            f"Deleted sequencing request '{seq_request.name}'", "success"
        ),
    )


@router.post("/{seq_request_id}/archive")
def archive_seq_request(
    seq_request_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

    if (
        seq_request.status_id != C.SeqRequestStatus.DRAFT.id
        and access_level < C.AccessLevel.INSIDER
    ):
        raise exc.NoPermissionsException()

    seq_request.status_id = C.SeqRequestStatus.ARCHIVED.id
    session.save(seq_request)

    return responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
        flash=responses.flash(
            f"Archived sequencing request '{seq_request.name}'", "success"
        ),
    )


@router.post("/{seq_request_id}/unarchive")
def unarchive_seq_request(
    seq_request_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

    seq_request.status_id = C.SeqRequestStatus.DRAFT.id
    seq_request.timestamp_submitted_utc = None
    session.save(seq_request)

    return responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
        flash=responses.flash(
            f"Unarchived sequencing request '{seq_request.name}'", "success"
        ),
    )


@router.get("/{seq_request_id}/export")
def export_seq_request(
    seq_request_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

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

    libraries_df = session.pd.get_seq_request_libraries(
        seq_request_id, include_indices=True
    )
    features_df = session.pd.get_seq_request_features(seq_request_id)

    bytes_io = BytesIO()
    with pd.ExcelWriter(bytes_io, engine="openpyxl") as writer:
        metadata_df.to_excel(writer, sheet_name="metadata", index=True)
        libraries_df.to_excel(writer, sheet_name="libraries", index=False)
        features_df.to_excel(writer, sheet_name="features", index=False)
    bytes_io.seek(0)

    return Response(
        bytes_io,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=request_{seq_request_id}.xlsx"
        },
    )


@router.get("/{seq_request_id}/export-libraries")
def export_seq_request_libraries(
    seq_request_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
    libraries_df = session.pd.get_seq_request_libraries(
        seq_request_id, include_indices=True
    )

    return Response(
        libraries_df.to_csv(sep="\t", index=False).encode("utf-8"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=libraries_{seq_request.id}.tsv"
        },
    )


@router.post("/{seq_request_id}/clone", dependencies=[Depends(dependencies.seq_request_permissions)])
def clone_seq_request(
    seq_request_id: int,
    request: Request,
    method: Literal["pooled", "indexed", "raw"] = Query(...),
    session: SyncSession = Depends(dependencies.db_session),
):
    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
    cloned_request = actions.clone_seq_request(session=session, seq_request=seq_request, method=method)
    cloned_request.status = C.SeqRequestStatus.DRAFT
    return responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=cloned_request.id),
        flash=responses.flash("Request cloned", "success"),
    )


@router.delete("/{seq_request_id}/remove-all-libraries")
def remove_all_seq_request_libraries(
    seq_request_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

    if (
        seq_request.status_id != C.SeqRequestStatus.DRAFT.id
        and access_level < C.AccessLevel.INSIDER
    ):
        raise exc.NoPermissionsException()

    for library in seq_request.libraries:
        session.delete(library)

    return responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request_id),
        flash=responses.flash(
            f"Removed all libraries from sequencing request '{seq_request.name}'",
            "success",
        ),
    )


@router.get("/{seq_request_id}/overview")
def render_seq_request_overview(
    seq_request_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[
            orm.selectinload(models.SeqRequest.samples).selectinload(models.Sample.project),
            orm.selectinload(models.SeqRequest.samples).selectinload(models.Sample.library_links).selectinload(models.links.SampleLibraryLink.library).selectinload(models.Library.pool),
            orm.selectinload(models.SeqRequest.samples).selectinload(models.Sample.library_links).selectinload(models.links.SampleLibraryLink.library).with_expression(models.Library._num_samples, models.Library.num_samples.expression),
        ],
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
            project_node = {
                "node": idx,
                "name": sample.project.title,
                "id": f"project-{sample.project_id}",
            }
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

                        pool_link_widths[link.library.pool.id] += (
                            LINK_WIDTH_UNIT * link.library.num_samples
                        )
                        links.append(
                            {
                                "source": library_nodes[link.library.id],
                                "target": pool_idx,
                                "value": LINK_WIDTH_UNIT * link.library.num_samples,
                            }
                        )
                else:
                    library_idx = library_nodes[link.library.id]

                links.append(
                    {
                        "source": sample_node["node"],
                        "target": library_idx,
                        "value": LINK_WIDTH_UNIT,
                    }
                )

        links.append(
            {
                "source": project_idx,
                "target": sample_nodes[sample.id],
                "value": LINK_WIDTH_UNIT * n_sample_links,
            }
        )

    return responses.htmx_response(
        "components/plots/request_overview.html",
        nodes=nodes,
        links=links,
        contains_pooled=contains_pooled,
    )


@router.get("/{seq_request_id}/assignees")
def render_seq_request_assignee_table(
    seq_request_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.assignees)],
    )

    return responses.htmx_response(
        "components/tables/seq_request-assignee.html",
        assignees=seq_request.assignees,
        seq_request=seq_request,
    )


@router.delete("/{seq_request_id}/remove-assignee/{assignee_id}")
def remove_seq_request_assignee(
    seq_request_id: int,
    assignee_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.assignees)],
    )

    assignee = session.get_one(Q.user.select(id=assignee_id))

    if assignee not in seq_request.assignees:
        raise exc.BadRequestException()

    seq_request.assignees.remove(assignee)
    session.save(seq_request)

    return responses.htmx_response(
        "components/tables/seq_request-assignee.html",
        assignees=seq_request.assignees,
        seq_request=seq_request,
    )


@router.get("/{seq_request_id}/submit-checklist")
def get_seq_request_submit_checklist(
    seq_request_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id).options(
            orm.selectinload(models.SeqRequest.seq_auth_form_file),
            orm.selectinload(models.SeqRequest.contact_person),
            orm.with_expression(
                models.SeqRequest._num_samples, models.SeqRequest.num_samples.expression
            ),
            orm.with_expression(
                models.SeqRequest._num_libraries,
                models.SeqRequest.num_libraries.expression,
            ),
            orm.with_expression(
                models.SeqRequest._library_types,
                models.SeqRequest.library_types.expression,
            ),
            orm.with_expression(
                models.SeqRequest._library_type_counts,
                models.SeqRequest.library_type_counts.expression,
            ),
        )
    )
    checklist = seq_request.get_submit_checklist()

    return responses.htmx_response(
        "components/checklists/seq_request-submit.html",
        seq_request=seq_request,
        **checklist,
    )


@router.get("/{seq_request_id}/review-checklist")
def get_seq_request_review_checklist(
    seq_request_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[
            orm.selectinload(models.SeqRequest.requestor),
            orm.selectinload(models.SeqRequest.contact_person),
            orm.selectinload(models.SeqRequest.organization_contact),
            orm.selectinload(models.SeqRequest.bioinformatician_contact),
            orm.selectinload(models.SeqRequest.billing_contact),
            orm.selectinload(models.SeqRequest.samples).selectinload(models.Sample.project),
            orm.selectinload(models.SeqRequest.samples).selectinload(models.Sample.library_links).selectinload(models.links.SampleLibraryLink.library),
            orm.selectinload(models.SeqRequest.libraries).selectinload(models.Library.pool),
            orm.selectinload(models.SeqRequest.libraries).selectinload(models.Library.indices),
            orm.selectinload(models.SeqRequest.sample_library_links).selectinload(models.links.SampleLibraryLink.library),
            orm.selectinload(models.SeqRequest.sample_library_links).selectinload(models.links.SampleLibraryLink.sample),
            orm.selectinload(models.SeqRequest.seq_auth_form_file)
        ],
    )

    checklist: dict = seq_request.get_review_checklist()
    contains_mux_samples = any(library.is_multiplexed() for library in seq_request.libraries)

    indices_checked = True
    for library in seq_request.libraries:
        for index in library.indices:
            if (
                index.orientation is None
                or index.orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED
            ):
                indices_checked = False
                break
        if not indices_checked:
            break

    return responses.htmx_response(
        "components/checklists/seq_request-review.html",
        seq_request=seq_request,
        contains_mux_samples=contains_mux_samples,
        indices_checked=indices_checked,
        **checklist,
    )


@router.post("/{seq_request_id}/review-check/{step}")
def check_seq_request_review_step(
    seq_request_id: int,
    step: str,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

    if seq_request.review_checklist is None:
        seq_request.review_checklist = {}
    seq_request.review_checklist[step] = True
    session.save(seq_request)

    return responses.htmx_response(
        redirect=request.url_for(
            "seq_request_page", seq_request_id=seq_request.id, tab="review-tab"
        ),
    )


@router.post("/{seq_request_id}/review-uncheck/{step}")
def uncheck_seq_request_review_step(
    seq_request_id: int,
    step: str,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

    if seq_request.review_checklist is None:
        seq_request.review_checklist = {}
    seq_request.review_checklist[step] = False
    session.save(seq_request)

    return responses.htmx_response(
        redirect=request.url_for(
            "seq_request_page", seq_request_id=seq_request.id, tab="review-tab"
        ),
    )


@router.get("/{seq_request_id}/sample-table")
def get_seq_request_sample_table(
    seq_request_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
    df = session.pd.get_seq_request_sample_table(seq_request_id=seq_request_id)
    df["project"] = df["project_identifier"]
    df.loc[df["project"].isna(), "project"] = df.loc[
        df["project"].isna(), "project_title"
    ]
    df = df.drop(columns=["project_identifier", "project_title", "sample_id"])

    from ...components.tables import StaticSpreadsheet
    from ...components.tables.spreadsheet import TextColumn

    columns: list = [TextColumn("sample_name", "Sample Name", width=300)]
    for column in df.columns:
        if column not in {"sample_name", "project"}:
            columns.append(
                TextColumn(column, column.replace("_", " ").title(), width=200)
            )

    spreadsheet = StaticSpreadsheet(df, columns=columns)

    return responses.htmx_response(
        "components/itable.html", seq_request=seq_request, spreadsheet=spreadsheet
    )


@router.post("/{seq_request_id}/confirm-barcodes")
def confirm_seq_request_barcodes(
    seq_request_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.INSIDER:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[
            orm.selectinload(models.SeqRequest.libraries).selectinload(
                models.Library.indices
            ),
        ],
    )

    for library in seq_request.libraries:
        for index in library.indices:
            if (
                index.orientation is None
                or index.orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED
            ):
                index.orientation = C.BarcodeOrientation.FORWARD

    session.save(seq_request)

    return responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
    )


@router.delete("/{seq_request_id}/remove-share-email/{email}")
def remove_seq_request_share_email(
    seq_request_id: int,
    email: str,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.delivery_email_links)],
    )

    if len(seq_request.delivery_email_links) == 1:
        raise exc.NoPermissionsException()

    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    share_email_link = session.first(
        Q.links.get_seq_request_delivery_email_link(
            seq_request_id=seq_request_id, email=email
        )
    )
    if share_email_link is None:
        raise exc.ItemNotFoundException()

    session.delete(share_email_link)

    return responses.htmx_response(
        redirect=request.url_for(
            "seq_request_page", seq_request_id=seq_request.id, tab="request-share-tab"
        ),
        flash=responses.flash("Removed email!", "success"),
    )


@router.post("/{seq_request_id}/add-assignee")
def add_assignee_to_seq_request(
    seq_request_id: int,
    assignee_id: int | None = Query(None),
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    """Add an assignee to a SeqRequest."""
    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

    if assignee_id is not None:
        assignee = session.get_one(Q.user.select(id=assignee_id))
    else:
        assignee = current_user

    if not assignee.is_insider:
        raise exc.NoPermissionsException("Assignee must be an insider.")

    if assignee in seq_request.assignees:
        raise exc.BadRequestException("User is already an assignee.")

    seq_request.assignees.append(assignee)
    session.save(seq_request)

    return responses.htmx_response(redirect=responses.url_for("dashboard"), flash=responses.flash("Assignee Added!", "success"))


@router.delete("/{seq_request_id}/delete-file/{file_id}")
def delete_file(
    seq_request_id: int,
    file_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

    if (
        seq_request.status_id != C.SeqRequestStatus.DRAFT.id
        and access_level < C.AccessLevel.INSIDER
    ):
        raise exc.NoPermissionsException()

    file = session.get_one(Q.media_file.select(id=file_id))

    if file not in seq_request.media_files:
        raise exc.BadRequestException()

    file_path = os.path.join(config.settings.app_config.media_folder, file.path)
    if os.path.exists(file_path):
        os.remove(file_path)

    session.delete(file)

    return responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request_id),
        flash=responses.flash(f"Deleted file '{file.name}' from request.", "success"),
    )


@router.delete("/{seq_request_id}/remove-auth-form")
def remove_auth_form(
    seq_request_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
    current_user: models.User = Depends(dependencies.require_user),
):
    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.seq_auth_form_file)],
    )

    if seq_request.seq_auth_form_file is None:
        raise exc.BadRequestException("No authorization form uploaded.")

    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    if (
        seq_request.status_id != C.SeqRequestStatus.DRAFT.id
        and access_level < C.AccessLevel.INSIDER
    ):
        raise exc.NoPermissionsException()

    if (
        seq_request.status_id != C.SeqRequestStatus.DRAFT.id
        and not current_user.is_insider
    ):
        raise exc.NoPermissionsException()

    file = seq_request.seq_auth_form_file
    filepath = os.path.join(config.settings.app_config.media_folder, file.path)
    if os.path.exists(filepath):
        os.remove(filepath)

    session.delete(file)

    return responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
        flash=responses.flash("Authorization form removed!", "success"),
    )


@router.delete("/{seq_request_id}/remove-library/{library_id}")
def remove_library_from_request(
    seq_request_id: int,
    library_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

    if (
        seq_request.status_id != C.SeqRequestStatus.DRAFT.id
        and access_level < C.AccessLevel.INSIDER
    ):
        raise exc.NoPermissionsException()

    library = session.get_one(Q.library.select(id=library_id))

    if library.seq_request_id != seq_request.id:
        raise exc.BadRequestException()

    session.delete(library)

    return responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request_id),
        flash=responses.flash("Library removed!", "success"),
    )


@router.post("/{seq_request_id}/reseq-library/{library_id}")
def reseq_library(
    seq_request_id: int,
    library_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

    if (
        seq_request.status_id != C.SeqRequestStatus.DRAFT.id
        and access_level < C.AccessLevel.INSIDER
    ):
        raise exc.NoPermissionsException()

    library = session.get_one(Q.library.select(id=library_id))

    actions.clone_library(
        session=session,
        library_id=library.id,
        seq_request_id=seq_request.id,
        status=C.LibraryStatus.PREPARING,
        indexed=True,
    )

    return responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request_id),
        flash=responses.flash("Library cloned!", "success"),
    )


@router.delete("/{seq_request_id}/remove-sample/{sample_id}")
def remove_sample_from_request(
    seq_request_id: int,
    sample_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    sample = session.get_one(Q.sample.select(id=sample_id))

    for library_link in sample.library_links:
        if library_link.library.seq_request_id != seq_request_id:
            continue
        session.delete(library_link.library)

    return responses.htmx_response(
        redirect=request.url_for("seq_request_page", seq_request_id=seq_request_id),
        flash=responses.flash(
            "Removed all libraries associated with the sample.", "success"
        ),
    )

@router.get("/{seq_request_id}/add-share-email")
def render_add_share_email_form(
    seq_request_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
    form = forms.actions.SeqRequestShareEmailForm(request, seq_request=seq_request)
    return form.make_response()


@router.post("/{seq_request_id}/add-share-email")
def add_share_email(
    seq_request_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException()

    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id),
        options=[orm.selectinload(models.SeqRequest.delivery_email_links)],
    )
    form = forms.actions.SeqRequestShareEmailForm(request, seq_request=seq_request)
    form.validate()

    email = form.email.data.strip()
    if email in [link.email for link in seq_request.delivery_email_links]:
        form.email.errors.append("This email address is already in the list.")
        raise exc.FormValidationException(form)

    seq_request.delivery_email_links.append(
        models.links.SeqRequestDeliveryEmailLink(email=email)
    )
    session.save(seq_request)

    return responses.htmx_response(
        redirect=request.url_for(
            "seq_request_page", seq_request_id=seq_request.id, tab="request-share-tab"
        ),
        flash=responses.flash("Email added to the list.", "success"),
    )


@router.get("/{seq_request_id}/add-assignee-form")
def render_add_assignee_form(
    seq_request_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id).options(
            orm.selectinload(models.SeqRequest.assignees)
        ),
    )
    form = forms.actions.AddSeqRequestAssigneeForm(request, seq_request=seq_request, current_user=current_user)
    return form.make_response()


@router.post("/{seq_request_id}/add-assignee-form")
def add_assignee_to_seq_request_from_form(response=Depends(forms.actions.AddSeqRequestAssigneeForm.add_assignee)): return response