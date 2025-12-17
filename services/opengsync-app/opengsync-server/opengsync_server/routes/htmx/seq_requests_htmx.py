import os
import json
from io import BytesIO
from typing import Literal

from flask import Blueprint, url_for, render_template, flash, request, Response
from flask_htmx import make_response
import pandas as pd

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import (
    SeqRequestStatus, LibraryStatus,
    SampleStatus, SubmissionType, PoolStatus, AccessType,
    DataPathType
)

from ... import db, forms, logger, logic
from ...core import wrappers, exceptions
from ...core.RunTime import runtime


seq_requests_htmx = Blueprint("seq_requests_htmx", __name__, url_prefix="/htmx/seq_requests/")


@wrappers.htmx_route(seq_requests_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get(current_user: models.User):
    context = logic.seq_request.get_table_context(current_user=current_user, request=request)
    return make_response(render_template(**context))


@wrappers.htmx_route(seq_requests_htmx, db=db)
def export(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.VIEW:
        raise exceptions.NoPermissionsException()

    file_name = f"request_{seq_request_id}.xlsx"

    metadata = {
        "Name": [seq_request.name],
        "Description": [seq_request.description],
        "Requestor": [seq_request.requestor.name],
        "Requestor Email": [seq_request.requestor.email],
        "Submission Type": [seq_request.submission_type.name],
        "Organization": [seq_request.organization_contact.name],
        "Organization Address": [seq_request.organization_contact.address],
        "Contact Person": [seq_request.contact_person.name],
        "Contact Person Email": [seq_request.contact_person.email],
        "Contact Person Phone": [seq_request.contact_person.phone],
    }

    if seq_request.group is not None:
        metadata["Group"] = [seq_request.group.name]
        metadata["Group ID"] = [seq_request.group.id]
    
    if seq_request.billing_code is not None:
        metadata["Billing Code"] = [seq_request.billing_code]
        
    metadata_df = pd.DataFrame.from_records(metadata).T

    libraries_df = db.pd.get_seq_request_libraries(seq_request_id, include_indices=True)
    features_df = db.pd.get_seq_request_features(seq_request_id)

    bytes_io = BytesIO()
    # TODO: export features, CMOs, VISIUM metadata, etc...
    with pd.ExcelWriter(bytes_io, engine="openpyxl") as writer:  # type: ignore
        metadata_df.to_excel(writer, sheet_name="metadata", index=True)
        libraries_df.to_excel(writer, sheet_name="libraries", index=False)
        features_df.to_excel(writer, sheet_name="features", index=False)

    bytes_io.seek(0)
        
    return Response(
        bytes_io, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )


@wrappers.htmx_route(seq_requests_htmx, db=db)
def export_libraries(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
        
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
        
    file_name = f"libraries_{seq_request.id}.tsv"
    libraries_df = db.pd.get_seq_request_libraries(seq_request_id=seq_request_id, include_indices=True)

    return Response(
        libraries_df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)

    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()

    if request.method == "GET":
        form = forms.models.SeqRequestForm(form_type="edit", seq_request=seq_request)
        return form.make_response()

    return forms.models.SeqRequestForm(form_type="edit", seq_request=seq_request, formdata=request.form).process_request(user=current_user)


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["DELETE"])
def delete(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)

    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.ADMIN:
        raise exceptions.NoPermissionsException()

    db.seq_requests.delete(seq_request_id)

    flash(f"Deleted sequencing request '{seq_request.name}'", "success")
    return make_response(
        redirect=url_for("seq_requests_page.seq_requests"),
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"])
def archive(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)

    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    seq_request.status = SeqRequestStatus.ARCHIVED
    db.seq_requests.update(seq_request)
    flash(f"Archived sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Archived sequencing request '{seq_request.name}'")
    return make_response(
        redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request.id),
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"])
def unarchive(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    seq_request.status = SeqRequestStatus.DRAFT
    seq_request.timestamp_submitted_utc = None
    db.seq_requests.update(seq_request)

    flash(f"Unarchived sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Unarchived sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request.id),
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["GET", "POST"])
def submit_request(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if seq_request.status != SeqRequestStatus.DRAFT:
        raise exceptions.BadRequestException("Only draft requests can be submitted.")
    
    if not seq_request.is_submittable() and not current_user.is_insider():
        raise exceptions.BadRequestException("Request is missing prerequisites for submission.")

    access_type = db.seq_requests.get_access_type(seq_request, current_user)

    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if request.method == "GET":
        form = forms.SubmitSeqRequestForm(seq_request=seq_request)
        return form.make_response()
    else:
        form = forms.SubmitSeqRequestForm(seq_request=seq_request, formdata=request.form)
        return form.process_request(user=current_user)


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["GET", "POST"])
def create(current_user: models.User):
    if request.method == "GET":
        form = forms.models.SeqRequestForm(form_type="create")
        return form.make_response()
    
    return forms.models.SeqRequestForm(form_type="create", formdata=request.form).process_request(user=current_user)


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"])
def upload_auth_form(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)

    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if seq_request.status == SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()

    return forms.SeqAuthForm(
        seq_request=seq_request, formdata=request.form | request.files
    ).process_request(
        user=current_user
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["GET", "POST"])
def comment_form(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)

    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if request.method == "GET":
        form = forms.comment.SeqRequestCommentForm(seq_request=seq_request)
        return form.make_response()
    elif request.method == "POST":
        form = forms.comment.SeqRequestCommentForm(seq_request=seq_request, formdata=request.form)
        return form.process_request(current_user)
    else:
        raise exceptions.MethodNotAllowedException()


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["GET", "POST"])
def file_form(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
        
    if request.method == "GET":
        form = forms.file.SeqRequestAttachmentForm(seq_request=seq_request)
        return form.make_response()
    elif request.method == "POST":
        form = forms.file.SeqRequestAttachmentForm(seq_request=seq_request, formdata=request.form | request.files)
        return form.process_request(current_user)
    else:
        raise exceptions.MethodNotAllowedException()


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["DELETE"])
def delete_file(current_user: models.User, seq_request_id: int, file_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()

    if (file := db.media_files.get(file_id)) is None:
        raise exceptions.NotFoundException()
    
    if file not in seq_request.media_files:
        raise exceptions.BadRequestException()
    
    file_path = os.path.join(runtime.app.media_folder, file.path)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.media_files.delete(file_id=file.id)

    logger.info(f"Deleted file '{file.name}' from request (id='{seq_request_id}')")
    flash(f"Deleted file '{file.name}' from request.", "success")
    return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request_id))


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["DELETE"])
def remove_auth_form(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if seq_request.seq_auth_form_file is None:
        raise exceptions.BadRequestException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
        
    if seq_request.status != SeqRequestStatus.DRAFT:
        if not current_user.is_insider():
            raise exceptions.NoPermissionsException()
        
    file = seq_request.seq_auth_form_file

    filepath = os.path.join(runtime.app.media_folder, file.path)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.media_files.delete(file_id=file.id)

    flash("Authorization form removed!", "success")
    logger.debug(f"Removed sequencing authorization form for sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request.id),
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["DELETE"])
def remove_library(current_user: models.User, seq_request_id: int, library_id: int):    
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    if not current_user.is_insider():
        if seq_request.status != SeqRequestStatus.DRAFT:
            raise exceptions.NoPermissionsException()

    try:
        library_id = int(library_id)
    except ValueError:
        raise exceptions.BadRequestException()
    
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()

    if library.seq_request_id != seq_request.id:
        raise exceptions.BadRequestException()
        
    db.libraries.delete(library)
    flash("Library Removed!.", "success")

    context = logic.library.get_table_context(current_user=current_user, request=request, seq_request=seq_request)
    return make_response(render_template(**context))


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"], arg_params=["library_id"])
def reseq_library(current_user: models.User, seq_request_id: int, library_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    if not current_user.is_insider():
        if seq_request.status != SeqRequestStatus.DRAFT:
            raise exceptions.NoPermissionsException()
    
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
        
    db.libraries.clone(library_id=library.id, seq_request_id=seq_request.id, status=LibraryStatus.PREPARING, indexed=True)
    flash(f"Library Cloned!", "success")

    context = logic.library.get_table_context(current_user=current_user, request=request, seq_request=seq_request)
    return make_response(render_template(**context))


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["DELETE"], arg_params=["sample_id"])
def remove_sample(current_user: models.User, seq_request_id: int, sample_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    if (sample := db.samples.get(sample_id)) is None:
        raise exceptions.NotFoundException()

    for library_link in sample.library_links:
        if library_link.library.seq_request_id != seq_request_id:
            continue
        db.libraries.delete(library_link.library, delete_orphan_samples=False)

    flash("Removed all libraries associated with the sample.", "success")
    context = logic.sample.get_table_context(current_user=current_user, request=request, seq_request=seq_request)
    return make_response(render_template(**context))
        

@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["DELETE"])
def remove_all_libraries(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()

    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()

    for library in seq_request.libraries:
        db.libraries.delete(library)

    flash(f"Removed all libraries from sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Removed all libraries from sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request_id),
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"])
def query(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    field_name = next(iter(request.form.keys()))
    word = request.form.get(field_name, default="")
    
    results = db.seq_requests.query(name=word)

    return make_response(
        render_template(
            "components/search/seq_request.html",
            results=results,
            field_name=field_name
        )
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["GET", "POST"])
def process_request(current_user: models.User, seq_request_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        form = forms.ProcessRequestForm(seq_request=seq_request)
        return form.make_response()
    else:
        return forms.ProcessRequestForm(formdata=request.form, seq_request=seq_request).process_request(user=current_user)


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["GET", "POST"])
def add_share_email(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()

    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        form = forms.SeqRequestShareEmailForm(seq_request=seq_request)
        return form.make_response()
    
    return forms.SeqRequestShareEmailForm(seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["DELETE"])
def remove_share_email(current_user: models.User, seq_request_id: int, email: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if len(seq_request.delivery_email_links) == 1:
        raise exceptions.NoPermissionsException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
        
    db.seq_requests.remove_share_email(seq_request_id, email)

    flash(f"Removed email!", "success")
    return make_response(
        redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request.id, tab="request-share-tab"),
    )


@wrappers.htmx_route(seq_requests_htmx, db=db)
def overview(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()

    LINK_WIDTH_UNIT = 1

    samples, _ = db.samples.find(seq_request_id=seq_request_id, limit=None)
    
    nodes = []
    links = []
    contains_pooled = seq_request.submission_type == SubmissionType.POOLED_LIBRARIES

    idx = 0

    project_nodes: dict[int, int] = {}
    sample_nodes: dict[int, int] = {}
    library_nodes: dict[int, int] = {}
    pool_nodes: dict[int, int] = {}
    pool_link_widths: dict[int, int] = {}

    for sample in samples:
        if sample.project_id not in project_nodes.keys():
            project_node = {
                "node": idx,
                "name": sample.project.title,
                "id": f"project-{sample.project_id}"
            }
            nodes.append(project_node)
            project_nodes[sample.project.id] = idx
            project_idx = idx
            idx += 1
        else:
            project_idx = project_nodes[sample.project.id]

        sample_node = {
            "node": idx,
            "name": sample.name,
            "id": f"sample-{sample.id}"
        }
        nodes.append(sample_node)
        sample_nodes[sample.id] = idx
        idx += 1
        n_sample_links = 0
        for link in sample.library_links:
            if link.library.seq_request_id == seq_request_id:
                n_sample_links += 1
                if link.library.id not in library_nodes.keys():
                    library_node = {
                        "node": idx,
                        "name": link.library.type.identifier,
                        "id": f"library-{link.library.id}"
                    }
                    nodes.append(library_node)
                    library_nodes[link.library.id] = idx
                    library_idx = idx
                    idx += 1

                    if contains_pooled:
                        if link.library.pool_id not in pool_nodes.keys():
                            pool_node = {
                                "node": idx,
                                "name": link.library.pool.name,         # type: ignore
                                "id": f"pool-{link.library.pool.id}"    # type: ignore
                            }
                            nodes.append(pool_node)
                            pool_nodes[link.library.pool.id] = idx      # type: ignore
                            pool_link_widths[link.library.pool.id] = 0  # type: ignore
                            pool_idx = idx

                            idx += 1
                        else:
                            pool_idx = pool_nodes[link.library.pool.id]     # type: ignore

                        pool_link_widths[link.library.pool.id] += LINK_WIDTH_UNIT * link.library.num_samples    # type: ignore
                        
                        links.append({
                            "source": library_nodes[link.library_id],
                            "target": pool_idx,
                            "value": LINK_WIDTH_UNIT * link.library.num_samples
                        })
                else:
                    library_idx = library_nodes[link.library.id]
                links.append({
                    "source": sample_node["node"],
                    "target": library_idx,
                    "value": LINK_WIDTH_UNIT
                })

        links.append({
            "source": project_idx,
            "target": sample_nodes[sample.id],
            "value": LINK_WIDTH_UNIT * n_sample_links
        })

    return make_response(
        render_template(
            "components/plots/request_overview.html",
            nodes=nodes, links=links, contains_pooled=contains_pooled
        )
    )


@wrappers.htmx_route(seq_requests_htmx, db=db)
def get_data_paths(current_user: models.User, seq_request_id: int, page: int = 0):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()

    access_type = db.seq_requests.get_access_type(seq_request, current_user)
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

    data_paths, n_pages = db.data_paths.find(offset=offset, seq_request_id=seq_request_id, type_in=type_in, sort_by=sort_by, descending=descending, count_pages=True)

    return make_response(
        render_template(
            "components/tables/seq_request-data_path.html", data_paths=data_paths,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            seq_request=seq_request, type_in=type_in
        )
    )

@wrappers.htmx_route(seq_requests_htmx, db=db)
def get_comments(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()

    return make_response(
        render_template(
            "components/comment-list.html",
            comments=seq_request.comments
        )
    )


@wrappers.htmx_route(seq_requests_htmx, db=db)
def get_files(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()

    return make_response(
        render_template(
            "components/file-list.html",
            files=seq_request.media_files, seq_request=seq_request, delete="seq_requests_htmx.delete_file",
            delete_context={"seq_request_id": seq_request_id}
        )
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"])
def clone(current_user: models.User, seq_request_id: int, method: Literal["pooled", "indexed", "raw"]):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if method not in {"pooled", "indexed", "raw"}:
        raise exceptions.BadRequestException()

    cloned_request = db.seq_requests.clone(seq_request_id=seq_request.id, method=method)

    flash("Request cloned", "success")
    return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=cloned_request.id))


@wrappers.htmx_route(seq_requests_htmx, db=db)
def store_samples(current_user: models.User, seq_request_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()

    if seq_request.submission_type == SubmissionType.RAW_SAMPLES:
        form: forms.SelectSamplesForm = forms.SelectSamplesForm(
            workflow="store_samples",
            sample_status_filter=[SampleStatus.WAITING_DELIVERY],
            context=dict(seq_request=seq_request),
            select_samples=True, select_libraries=False, select_pools=False,
            selected_samples=[s for s in seq_request.samples if s.status == SampleStatus.WAITING_DELIVERY]
        )
    elif seq_request.submission_type == SubmissionType.POOLED_LIBRARIES:
        form: forms.SelectSamplesForm = forms.SelectSamplesForm(
            workflow="store_samples",
            pool_status_filter=[PoolStatus.ACCEPTED],
            context=dict(seq_request=seq_request),
            select_samples=False, select_libraries=False, select_pools=True,
            selected_pools=[pool for pool in seq_request.pools if pool.status == PoolStatus.ACCEPTED]
        )
    else:
        form: forms.SelectSamplesForm = forms.SelectSamplesForm(
            workflow="store_samples",
            library_status_filter=[LibraryStatus.ACCEPTED],
            context=dict(seq_request=seq_request),
            select_samples=False, select_libraries=True, select_pools=False,
            selected_libraries=[library for library in seq_request.libraries if library.status == LibraryStatus.ACCEPTED],
        )

    return form.make_response()


@wrappers.htmx_route(seq_requests_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get_recent(current_user: models.User, page: int = 0):
    PAGE_LIMIT = 10
    
    if current_user.is_insider():
        def __order_by_status_and_time(q):
            return q.order_by(
                models.SeqRequest.status_id,
                models.SeqRequest.timestamp_submitted_utc.desc()
            )

        seq_requests, _ = db.seq_requests.find(
            status_in=[SeqRequestStatus.SUBMITTED, SeqRequestStatus.ACCEPTED, SeqRequestStatus.SAMPLES_RECEIVED, SeqRequestStatus.PREPARED, SeqRequestStatus.DATA_PROCESSING],
            custom_query=__order_by_status_and_time, limit=PAGE_LIMIT, offset=PAGE_LIMIT * page
        )
    else:
        seq_requests, _ = db.seq_requests.find(
            user_id=current_user.id,
            sort_by="timestamp_submitted_utc",
            descending=True,
            limit=PAGE_LIMIT, offset=PAGE_LIMIT * page
        )

    return make_response(render_template(
        "components/dashboard/seq_requests-list.html", seq_requests=seq_requests,
        current_page=page, limit=PAGE_LIMIT
    ))

@wrappers.htmx_route(seq_requests_htmx, db=db)
def get_assignees(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    return make_response(
        render_template(
            "components/tables/seq_request-assignee.html",
            assignees=seq_request.assignees,
            seq_request=seq_request
        )
    )

@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"])
def add_assignee(current_user: models.User, seq_request_id: int, assignee_id: int | None = None):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
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
    
    if assignee in seq_request.assignees:
        raise exceptions.BadRequestException("User is already an assignee.")
    
    seq_request.assignees.append(assignee)
    db.seq_requests.update(seq_request)
    flash("Assignee Added.", "success")
    return make_response(redirect=url_for("dashboard"))

@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["GET", "POST"])
def add_assignee_form(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        form = forms.AddSeqRequestAssigneeForm(current_user=current_user, seq_request=seq_request)
        return form.make_response()
    else:
        return forms.AddSeqRequestAssigneeForm(formdata=request.form, current_user=current_user, seq_request=seq_request).process_request()

@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["DELETE"])
def remove_assignee(current_user: models.User, seq_request_id: int, assignee_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (assignee := db.users.get(assignee_id)) is None:
        raise exceptions.NotFoundException()
    
    if assignee not in seq_request.assignees:
        raise exceptions.BadRequestException()

    seq_request.assignees.remove(assignee)
    db.seq_requests.update(seq_request)

    flash("Assignee Removed.", "success")
    return make_response(
        render_template(
            "components/tables/seq_request-assignee.html",
            assignees=seq_request.assignees,
            seq_request=seq_request
        )
    )

@wrappers.htmx_route(seq_requests_htmx, db=db)
def checklist(current_user: models.User, seq_request_id: int):    
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    checklist = seq_request.get_checklist()
    return make_response(
        render_template(
            "components/checklists/seq_request.html",
            seq_request=seq_request, **checklist
        )
    )