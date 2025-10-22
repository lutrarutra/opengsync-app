import os
import json
from io import BytesIO
from typing import Literal

from flask import Blueprint, url_for, render_template, flash, request, Response
from flask_htmx import make_response
import pandas as pd

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import (
    SeqRequestStatus, LibraryStatus, LibraryType,
    SampleStatus, SubmissionType, PoolStatus, ProjectStatus, AccessType,
    DataPathType
)

from ... import db, forms, logger
from ...core import wrappers, exceptions
from ...core.RunTime import runtime


seq_requests_htmx = Blueprint("seq_requests_htmx", __name__, url_prefix="/htmx/seq_requests/")


@wrappers.htmx_route(seq_requests_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get(current_user: models.User, page: int = 0):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SeqRequestStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
        
        if len(status_in) == 0:
            status_in = None

    if (submission_type_in := request.args.get("submission_type_id_in")) is not None:
        submission_type_in = json.loads(submission_type_in)
        try:
            submission_type_in = [SubmissionType.get(int(submission_type)) for submission_type in submission_type_in]
        except ValueError:
            raise exceptions.BadRequestException()
        
        if len(submission_type_in) == 0:
            submission_type_in = None
    
    seq_requests: list[models.SeqRequest] = []

    user_id = current_user.id if not current_user.is_insider() else None

    seq_requests, n_pages = db.seq_requests.find(
        offset=offset, user_id=user_id, sort_by=sort_by, descending=descending,
        submission_type_in=submission_type_in,
        show_drafts=True, status_in=status_in, count_pages=True
    )

    return make_response(
        render_template(
            "components/tables/seq_request.html",
            seq_requests=seq_requests,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            SeqRequestStatus=SeqRequestStatus,
            status_in=status_in,
            submission_type_in=submission_type_in,
        )
    )


@wrappers.htmx_route(seq_requests_htmx, db=db)
def get_form(current_user: models.User, form_type: Literal["create", "edit"]):
    if form_type not in ["create", "edit"]:
        raise exceptions.BadRequestException()
    
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if form_type != "edit":
            raise exceptions.BadRequestException()
        
        if (seq_request := db.seq_requests.get(seq_request_id)) is None:
            raise exceptions.NotFoundException()
        
        if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
            raise exceptions.NoPermissionsException()
        return forms.models.SeqRequestForm(form_type=form_type, seq_request=seq_request).make_response()
    
    # seq_request_id must be provided if form_type is "edit"
    if form_type == "edit":
        raise exceptions.BadRequestException()

    return forms.models.SeqRequestForm(form_type=form_type, current_user=current_user).make_response()


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


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"])
def edit(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)

    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()

    return forms.models.SeqRequestForm(form_type="edit", formdata=request.form).process_request(
        seq_request=seq_request, user=current_user
    )


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
        raise exceptions.NoPermissionsException()
    
    if not seq_request.is_submittable():
        raise exceptions.NoPermissionsException()

    access_type = db.seq_requests.get_access_type(seq_request, current_user)

    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    if request.method == "GET":
        form = forms.SubmitSeqRequestForm(seq_request=seq_request)
        return form.make_response()
    else:
        form = forms.SubmitSeqRequestForm(seq_request=seq_request, formdata=request.form)
        return form.process_request(user=current_user)


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"])
def create(current_user: models.User):
    return forms.models.SeqRequestForm(form_type="create", formdata=request.form).process_request(user=current_user, seq_request=None)


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
def remove_library(current_user: models.User, seq_request_id: int, page: int = 0):
    if (library_id := request.args.get("library_id")) is None:
        raise exceptions.BadRequestException()
    
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
        
    db.libraries.delete(library)

    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    libraries, n_pages = db.libraries.find(
        page=page, seq_request_id=seq_request_id, sort_by=sort_by, descending=descending,
        status_in=status_in, type_in=type_in
    )

    return make_response(
        render_template(
            "components/tables/seq_request-library.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, seq_request=seq_request,
            status_in=status_in, type_in=type_in
        )
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["DELETE"], arg_params=["sample_id"])
def remove_sample(current_user: models.User, seq_request_id: int, sample_id: int, page: int = 0):
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

    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    samples, n_pages = db.samples.find(
        page=page, seq_request_id=seq_request_id, sort_by=sort_by, descending=descending,
        status_in=status_in
    )

    return make_response(
        render_template(
            "components/tables/seq_request-sample.html",
            samples=samples, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, seq_request=seq_request,
            status_in=status_in
        )
    )
        

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

@wrappers.htmx_route(seq_requests_htmx, db=db)
def table_query(current_user: models.User):
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    elif (word := request.args.get("requestor_id")) is not None:
        field_name = "requestor_id"
    elif (word := request.args.get("group_id")) is not None:
        field_name = "group_id"
    else:
        raise exceptions.BadRequestException()
    
    user_id = current_user.id if not current_user.is_insider() else None

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SeqRequestStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
        
        if len(status_in) == 0:
            status_in = None

    seq_requests: list[models.SeqRequest] = []
    if field_name == "name":
        seq_requests = db.seq_requests.query(name=word, user_id=user_id, status_in=status_in)
    elif field_name == "id":
        try:
            _id = int(word)
            if (seq_request := db.seq_requests.get(_id)) is not None:
                if user_id is None or seq_request.requestor_id == user_id:
                    seq_requests = [seq_request]
                if status_in is not None and seq_request.status not in status_in:
                    seq_requests = []
        except ValueError:
            pass
    elif field_name == "requestor_id":
        seq_requests = db.seq_requests.query(requestor=word, user_id=user_id, status_in=status_in)
    elif field_name == "group_id":
        seq_requests = db.seq_requests.query(group=word, user_id=user_id, status_in=status_in)

    return make_response(
        render_template(
            "components/tables/seq_request.html",
            current_query=word, active_query_field=field_name,
            seq_requests=seq_requests, status_in=status_in
        )
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"])
def process_request(current_user: models.User, seq_request_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    return forms.ProcessRequestForm(formdata=request.form).process_request(
        seq_request=seq_request, user=current_user
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["POST"])
def add_share_email(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()

    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.SeqRequestShareEmailForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


@wrappers.htmx_route(seq_requests_htmx, db=db, methods=["DELETE"])
def remove_share_email(current_user: models.User, seq_request_id: int, email: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if len(seq_request.delivery_email_links) == 1:
        raise exceptions.NoPermissionsException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if seq_request.status != SeqRequestStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
        
    db.seq_requests.remove_share_email(seq_request_id, email)

    flash(f"Removed shared email '{email}' from sequencing request '{seq_request.name}'", "success")
    return make_response(
        redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request.id),
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
    contains_pooled = False

    seq_request_node = {
        "node": 0,
        "name": seq_request.name,
        "id": f"seq_request-{seq_request.id}"
    }
    nodes.append(seq_request_node)

    idx = 1

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

                    if not link.library.is_pooled():
                        links.append({
                            "source": library_idx,
                            "target": seq_request_node["node"],
                            "value": LINK_WIDTH_UNIT * link.library.num_samples
                        })
                    else:
                        contains_pooled = True
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

    for pool_id, pool_node in pool_nodes.items():
        links.append({
            "source": pool_node,
            "target": seq_request_node["node"],
            "value": pool_link_widths[pool_id]
        })

    return make_response(
        render_template(
            "components/plots/request_overview.html",
            nodes=nodes, links=links, contains_pooled=contains_pooled
        )
    )


@wrappers.htmx_route(seq_requests_htmx, db=db)
def get_libraries(current_user: models.User, seq_request_id: int, page: int = 0):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    libraries, n_pages = db.libraries.find(
        page=page, seq_request_id=seq_request_id, sort_by=sort_by, descending=descending,
        status_in=status_in, type_in=type_in
    )

    return make_response(
        render_template(
            "components/tables/seq_request-library.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, seq_request=seq_request,
            status_in=status_in, type_in=type_in
        )
    )


@wrappers.htmx_route(seq_requests_htmx, db=db)
def get_projects(current_user: models.User, seq_request_id: int, page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Project.sortable_fields:
        raise exceptions.BadRequestException()

    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [ProjectStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
    
    projects, n_pages = db.projects.find(
        offset=offset, seq_request_id=seq_request_id, sort_by=sort_by,
        descending=descending, count_pages=True, status_in=status_in
    )

    return make_response(
        render_template(
            "components/tables/seq_request-project.html",
            projects=projects, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            seq_request=seq_request, status_in=status_in,
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
def query_libraries(current_user: models.User, seq_request_id: int):
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()
    
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    libraries: list[models.Library] = []
    if field_name == "name":
        libraries = db.libraries.query(name=word, seq_request_id=seq_request_id, status_in=status_in, type_in=type_in)
    elif field_name == "id":
        try:
            _id = int(word)
            if (library := db.libraries.get(_id)) is not None:
                if library.seq_request_id == seq_request_id:
                    libraries = [library]
                if status_in is not None and library.status not in status_in:
                    libraries = []
                if type_in is not None and library.type not in type_in:
                    libraries = []
        except ValueError:
            pass

    return make_response(
        render_template(
            "components/tables/seq_request-library.html",
            current_query=word, active_query_field=field_name,
            seq_request=seq_request,
            libraries=libraries, type_in=type_in, status_in=status_in
        )
    )


@wrappers.htmx_route(seq_requests_htmx, db=db)
def get_samples(current_user: models.User, seq_request_id: int, page: int = 0):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    samples, n_pages = db.samples.find(
        page=page, seq_request_id=seq_request_id, sort_by=sort_by, descending=descending,
        status_in=status_in
    )

    return make_response(
        render_template(
            "components/tables/seq_request-sample.html",
            samples=samples, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, seq_request=seq_request,
            status_in=status_in
        )
    )
    

@wrappers.htmx_route(seq_requests_htmx, db=db)
def get_pools(current_user: models.User, seq_request_id: int, page: int = 0):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.seq_requests.get_access_type(seq_request, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    pools, n_pages = db.pools.find(seq_request_id=seq_request_id, page=page, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            "components/tables/seq_request-pool.html",
            pools=pools, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, seq_request=seq_request
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
def get_recent_seq_requests(current_user: models.User, page: int = 0):
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
