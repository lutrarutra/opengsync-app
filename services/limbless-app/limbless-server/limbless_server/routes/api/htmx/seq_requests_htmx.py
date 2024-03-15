import os
from io import BytesIO
from typing import Optional, TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, abort, request, Response, jsonify, current_app
from flask_htmx import make_response
from flask_login import login_required
from werkzeug.utils import secure_filename
import pandas as pd

from limbless_db import models, DBSession, DBHandler, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, SeqRequestStatus
from limbless_db.core import exceptions
from .... import db, forms, logger

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user


seq_requests_htmx = Blueprint("seq_requests_htmx", __name__, url_prefix="/api/hmtx/seq_requests/")


@seq_requests_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.SeqRequest.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    seq_requests: list[models.SeqRequest] = []
    context = {}

    if (with_status := request.args.get("with_status", None)) is not None:
        try:
            with_status = SeqRequestStatus.get(int(with_status))
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        with_statuses = [with_status]
    else:
        with_statuses = None

    if (exclude_experiment_id := request.args.get("exclude_experiment_id", None)) is not None:
        try:
            exclude_experiment_id = int(exclude_experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        exclude_experiment_id = None

    if (user_id := request.args.get("user_id")) is not None:
        template = "components/tables/user-seq_request.html"
        try:
            user_id = int(user_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if user_id != current_user.id and not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (user := db.get_user(user_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)

        seq_requests, n_pages = db.get_seq_requests(
            offset=offset, user_id=user_id, sort_by=sort_by, descending=descending,
            with_statuses=with_statuses, exclude_experiment_id=exclude_experiment_id
        )
        context["user"] = user

    elif (sample_id := request.args.get("sample_id")) is not None:
        template = "components/tables/sample-seq_request.html"
        try:
            sample_id = int(sample_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if (sample := db.get_sample(sample_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if not current_user.is_insider():
            if sample.owner_id != current_user.id:
                return abort(HTTPResponse.FORBIDDEN.id)
        
        seq_requests, n_pages = db.get_seq_requests(
            offset=offset, sample_id=sample_id, sort_by=sort_by, descending=descending,
            with_statuses=with_statuses, exclude_experiment_id=exclude_experiment_id
        )
        context["sample"] = sample
    elif (experiment_id := request.args.get("experiment_id")) is not None:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        template = "components/tables/experiment-seq_request.html"
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if (experiment := db.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        seq_requests, n_pages = db.get_seq_requests(
            offset=offset, experiment_id=experiment_id, sort_by=sort_by, descending=descending,
            with_statuses=with_statuses, exclude_experiment_id=exclude_experiment_id
        )
        context["experiment"] = experiment
    else:
        template = "components/tables/seq_request.html"
        with DBSession(db) as session:
            if not current_user.is_insider():
                user_id = current_user.id
            else:
                user_id = None
            seq_requests, n_pages = session.get_seq_requests(
                offset=offset, user_id=user_id, sort_by=sort_by, descending=descending,
                show_drafts=True, with_statuses=with_statuses, exclude_experiment_id=exclude_experiment_id
            )

    return make_response(
        render_template(
            template, seq_requests=seq_requests,
            seq_requests_n_pages=n_pages, seq_requests_active_page=page,
            seq_requests_current_sort=sort_by, seq_requests_current_sort_order=order,
            **context
        ), push_url=False
    )


@seq_requests_htmx.route("<int:seq_request_id>/export", methods=["GET"])
@login_required
def export(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
        
    samples, _ = db.get_samples(seq_request_id=seq_request_id, limit=None)
    libraries, _ = db.get_libraries(seq_request_id=seq_request_id, limit=None)
    
    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HTTPResponse.FORBIDDEN.id)

    file_name = secure_filename(f"{seq_request.name}_request.xlsx")

    metadata_df = pd.DataFrame.from_records([seq_request.to_dict()]).T
    samples_df = pd.DataFrame.from_records([sample.to_dict() for sample in samples])
    libraries_df = pd.DataFrame.from_records([library.to_dict() for library in libraries])

    bytes_io = BytesIO()
    # TODO: export features, CMOs, VISIUM metadata, etc...
    with pd.ExcelWriter(bytes_io, engine="openpyxl") as writer:  # type: ignore
        metadata_df.to_excel(writer, sheet_name="metadata", index=True)
        samples_df.to_excel(writer, sheet_name="samples", index=False)
        libraries_df.to_excel(writer, sheet_name="libraries", index=False)

    bytes_io.seek(0)
    mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
    return Response(
        bytes_io, mimetype=mimetype,
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )


@seq_requests_htmx.route("<int:seq_request_id>/export_libraries", methods=["GET"])
@login_required
def export_libraries(seq_request_id: int):
    with DBSession(db) as session:
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        libraries = seq_request.libraries

    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    file_name = secure_filename(f"{seq_request.name}_libraries.tsv")

    df = pd.DataFrame.from_records([library.to_dict() for library in libraries])

    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )


@seq_requests_htmx.route("<int:seq_request_id>/edit", methods=["POST"])
@login_required
def edit(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HTTPResponse.FORBIDDEN.id)

    return forms.SeqRequestForm(request.form).process_request(
        seq_request=seq_request, user_id=current_user.id
    )


@seq_requests_htmx.route("<int:seq_request_id>/delete", methods=["DELETE"])
@login_required
def delete(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HTTPResponse.FORBIDDEN.id)

    db.delete_seq_request(seq_request_id)

    flash(f"Deleted sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Deleted sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_requests_page"),
    )


@seq_requests_htmx.route("<int:seq_request_id>/archive", methods=["POST"])
@login_required
def archive(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    seq_request.status_id = SeqRequestStatus.ARCHIVED.id
    seq_request = db.update_seq_request(seq_request)
    flash(f"Archived sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Archived sequencing request '{seq_request.name}'")
    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/unarchive", methods=["POST"])
@login_required
def unarchive(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    seq_request.status_id = SeqRequestStatus.DRAFT.id
    seq_request.submitted_time = None
    seq_request = db.update_seq_request(seq_request)

    flash(f"Unarchived sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Unarchived sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/edit", methods=["GET"])
@login_required
def submit(seq_request_id: int):
    with DBSession(db) as session:
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if seq_request.requestor_id != current_user.id:
            if not current_user.is_insider():
                return abort(HTTPResponse.FORBIDDEN.id)
        
        if not seq_request.is_submittable():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        session.submit_seq_request(seq_request_id)

    flash(f"Submitted sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Submitted sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("create", methods=["POST"])
@login_required
def create():
    return forms.SeqRequestForm(request.form).process_request(user_id=current_user.id)


@seq_requests_htmx.route("<int:seq_request_id>/upload_auth_form", methods=["POST"])
@login_required
def upload_auth_form(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if seq_request.requestor_id != current_user.id:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
    if seq_request.seq_auth_form_file_id is not None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    return forms.SeqAuthForm(request.form | request.files).process_request(
        seq_request=seq_request, user=current_user
    )


@seq_requests_htmx.route("<int:seq_request_id>/add_comment", methods=["POST"])
@login_required
def add_comment(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if seq_request.requestor_id != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    return forms.SeqRequestCommentForm(formdata=request.form, seq_request_id=seq_request_id).process_request(
        seq_request=seq_request, user=current_user
    )


@seq_requests_htmx.route("<int:seq_request_id>/upload_file", methods=["POST"])
@login_required
def upload_file(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not (seq_request.requestor_id == current_user.id or current_user.is_insider()):
        return abort(HTTPResponse.FORBIDDEN.id)
    
    return forms.SeqRequestAttachmentForm(seq_request_id=seq_request_id, formdata=request.form | request.files).process_request(
        seq_request=seq_request, user=current_user
    )


@seq_requests_htmx.route("<int:seq_request_id>/delete_file/<int:file_id>", methods=["DELETE"])
@login_required
def delete_file(seq_request_id: int, file_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not (seq_request.requestor_id == current_user.id or current_user.is_insider()):
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (file := db.get_file(file_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    db.remove_file_from_seq_request(seq_request_id, file_id)
    filepath = os.path.join(current_app.config["MEDIA_FOLDER"], file.path)
    if os.path.exists(filepath):
        os.remove(filepath)

    logger.info(f"Deleted file '{file.name}' from request (id='{seq_request_id}')")
    flash(f"Deleted file '{file.name}' from experrequestiment.", "success")
    return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request_id))


@seq_requests_htmx.route("<int:seq_request_id>/remove_auth_form", methods=["DELETE"])
@login_required
def remove_auth_form(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if seq_request.seq_auth_form_file_id is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if seq_request.requestor_id != current_user.id:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
    if seq_request.status != SeqRequestStatus.DRAFT:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)

    if (file := db.get_file(seq_request.seq_auth_form_file_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    filepath = os.path.join(current_app.config["MEDIA_FOLDER"], file.path)
    if os.path.exists(filepath):
        os.remove(filepath)

    seq_request.seq_auth_form_file_id = None
    seq_request = db.update_seq_request(seq_request=seq_request)

    db.remove_file_from_seq_request(seq_request_id, file.id)

    flash("Authorization form removed!", "success")
    logger.debug(f"Removed sequencing authorization form for sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/remove_library", methods=["DELETE"])
@login_required
def remove_library(seq_request_id: int):
    if (library_id := request.args.get("library_id")) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if seq_request.status != SeqRequestStatus.DRAFT:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
    
    try:
        library_id = int(library_id)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    with DBSession(db) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if seq_request.requestor_id != current_user.id:
            if not current_user.is_insider():
                return abort(HTTPResponse.FORBIDDEN.id)
            
        session.delete_library(library_id)

    flash(f"Removed library '{library.name}' from sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Removed library '{library.name}' from sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request_id),
    )


@seq_requests_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    if (word := request.form.get("name", None)) is not None:
        field_name = "name"
    elif (word := request.form.get("id", None)) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if word is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    def __get_seq_requests(
        session: DBHandler, word: str | int, field_name: str,
        user_id: Optional[int] = None
    ) -> list[models.SeqRequest]:
        seq_requests: list[models.SeqRequest] = []
        if field_name == "name":
            seq_requests = session.query_seq_requests(
                str(word), user_id=user_id
            )
        elif field_name == "id":
            try:
                _id = int(word)
                if (seq_request := session.get_seq_request(_id)) is not None:
                    if user_id is not None:
                        if seq_request.requestor_id == user_id:
                            seq_requests = [seq_request]
                    else:
                        seq_requests = [seq_request]
            except ValueError:
                pass
        else:
            assert False    # This should never happen

        return seq_requests
    
    context = {}
    if (user_id := request.args.get("user_id", None)) is not None:
        template = "components/tables/user-seq_request.html"
        try:
            user_id = int(user_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        with DBSession(db) as session:
            if (user := session.get_user(user_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            
            seq_requests = __get_seq_requests(session, word, field_name, user_id=user_id)
            context["user"] = user
    else:
        template = "components/tables/seq_request.html"

        with DBSession(db) as session:
            if not current_user.is_insider():
                user_id = current_user.id
            else:
                user_id = None
            seq_requests = __get_seq_requests(session, word, field_name, user_id=user_id)

    return make_response(
        render_template(
            template,
            current_query=word, field_name=field_name,
            seq_requests=seq_requests, **context
        ), push_url=False
    )
        

@seq_requests_htmx.route("<int:seq_request_id>/reverse_complement", methods=["POST"])
@login_required
def reverse_complement(seq_request_id: int):
    if (index := request.args.get("index", None)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    try:
        index = int(index)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    library_id = request.args.get("library_id", None)
    if library_id is not None:
        try:
            library_id = int(library_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
    if index < 1 or index > 4:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    with DBSession(db) as session:
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if seq_request.requestor_id != current_user.id:
            if not current_user.is_insider():
                return abort(HTTPResponse.FORBIDDEN.id)
            
        if library_id is not None:
            libraries = [session.get_library(library_id)]
        else:
            libraries = seq_request.libraries
        
        n_barcodes = 0
        for library in libraries:
            if index == 1 and library.index_1_sequence:
                library.index_1_sequence = models.Barcode.reverse_complement(library.index_1_sequence)
                n_barcodes += 1
            elif index == 2 and library.index_2_sequence:
                library.index_2_sequence = models.Barcode.reverse_complement(library.index_2_sequence)
                n_barcodes += 1
            elif index == 3 and library.index_3_sequence:
                library.index_3_sequence = models.Barcode.reverse_complement(library.index_3_sequence)
                n_barcodes += 1
            elif index == 4 and library.index_4_sequence:
                library.index_4_sequence = models.Barcode.reverse_complement(library.index_4_sequence)
                n_barcodes += 1
            
            library = session.update_library(library)

    flash(f"Reverse complemented index {index} of sequencing request '{seq_request.name}' in {n_barcodes} libraries.", "success")
    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request_id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/process_request", methods=["POST"])
@login_required
def process_request(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.ProcessRequestForm(formdata=request.form).process_request(
        seq_request=seq_request, user=current_user
    )


@seq_requests_htmx.route("<int:seq_request_id>/add_share_email", methods=["POST"])
@login_required
def add_share_email(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if seq_request.requestor_id != current_user.id:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
    
    logger.debug(request.form)
    return forms.SeqRequestShareEmailForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


@seq_requests_htmx.route("<int:seq_request_id>/remove_share_email/<string:email>", methods=["DELETE"])
@login_required
def remove_share_email(seq_request_id: int, email: str):
    with DBSession(db) as session:
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if len(seq_request.share_email_links) == 1:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    if seq_request.requestor_id != current_user.id:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
    try:
        db.remove_seq_request_share_email(seq_request_id, email)
    except exceptions.ElementDoesNotExist:
        return abort(HTTPResponse.NOT_FOUND.id)

    flash(f"Removed shared email '{email}' from sequencing request '{seq_request.name}'", "success")
    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/get_graph", methods=["GET"])
@login_required
def get_graph(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if seq_request.requestor_id != current_user.id:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)

    LINK_WIDTH_UNIT = 1

    with DBSession(db) as session:
        samples, _ = session.get_samples(seq_request_id=seq_request_id, limit=None)

        graph = {
            "nodes": [],
            "links": [],
            "pooled": 0,
        }

        seq_request_node = {
            "node": 0,
            "name": seq_request.name,
            "id": f"seq_request-{seq_request.id}"
        }
        graph["nodes"].append(seq_request_node)

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
                    "name": sample.project.name,
                    "id": f"project-{sample.project_id}"
                }
                graph["nodes"].append(project_node)
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
            graph["nodes"].append(sample_node)
            sample_nodes[sample.id] = idx
            idx += 1
            n_sample_links = 0
            for link in sample.library_links:
                if link.library.seq_request_id == seq_request_id:
                    n_sample_links += 1
                    if link.library.id not in library_nodes.keys():
                        library_node = {
                            "node": idx,
                            "name": link.library.type.description,
                            "id": f"library-{link.library.id}"
                        }
                        graph["nodes"].append(library_node)
                        library_nodes[link.library.id] = idx
                        library_idx = idx
                        idx += 1

                        if not link.library.is_pooled():
                            graph["links"].append({
                                "source": library_idx,
                                "target": seq_request_node["node"],
                                "value": LINK_WIDTH_UNIT
                            })
                        else:
                            graph["pooled"] = 1
                            if link.library.pool_id not in pool_nodes.keys():
                                pool_node = {
                                    "node": idx,
                                    "name": link.library.pool.name,         # type: ignore
                                    "id": f"pool-{link.library.pool.id}"    # type: ignore
                                }
                                graph["nodes"].append(pool_node)
                                pool_nodes[link.library.pool.id] = idx      # type: ignore
                                pool_link_widths[link.library.pool.id] = 0  # type: ignore
                                pool_idx = idx

                                idx += 1
                            else:
                                pool_idx = pool_nodes[link.library.pool.id]     # type: ignore

                            pool_link_widths[link.library.pool.id] += LINK_WIDTH_UNIT * link.library.num_samples    # type: ignore
                            
                            graph["links"].append({
                                "source": library_nodes[link.library_id],
                                "target": pool_idx,
                                "value": LINK_WIDTH_UNIT * link.library.num_samples
                            })
                    else:
                        library_idx = library_nodes[link.library.id]
                    graph["links"].append({
                        "source": sample_node["node"],
                        "target": library_idx,
                        "value": LINK_WIDTH_UNIT
                    })

            graph["links"].append({
                "source": project_idx,
                "target": sample_nodes[sample.id],
                "value": LINK_WIDTH_UNIT * n_sample_links
            })

    for pool_id, pool_node in pool_nodes.items():
        graph["links"].append({
            "source": pool_node,
            "target": seq_request_node["node"],
            "value": pool_link_widths[pool_id]
        })

    return make_response(
        jsonify(graph)
    )