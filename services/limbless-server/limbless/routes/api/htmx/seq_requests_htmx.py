import os
from io import StringIO, BytesIO
from uuid import uuid4
from typing import Optional, TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, abort, request, Response, jsonify
from flask_htmx import make_response
from flask_login import login_required
from werkzeug.utils import secure_filename
import pandas as pd

from .... import db, forms, logger, models, PAGE_LIMIT, SEQ_AUTH_FORMS_DIR
from ....core import DBSession, DBHandler
from ....categories import HttpResponse, SequencingType, FlowCellType, SeqRequestStatus

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user


seq_requests_htmx = Blueprint("seq_requests_htmx", __name__, url_prefix="/api/seq_requests/")


@seq_requests_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.SeqRequest.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    seq_requests: list[models.SeqRequest] = []
    context = {}

    if (with_status := request.args.get("with_status", None)) is not None:
        try:
            with_status = SeqRequestStatus.get(int(with_status))
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        with_statuses = [with_status]
    else:
        with_statuses = None

    if (exclude_experiment_id := request.args.get("exclude_experiment_id", None)) is not None:
        try:
            exclude_experiment_id = int(exclude_experiment_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
    else:
        exclude_experiment_id = None

    if (user_id := request.args.get("user_id")) is not None:
        template = "components/tables/user-seq_request.html"
        try:
            user_id = int(user_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        if user_id != current_user.id and not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        if (user := db.db_handler.get_user(user_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)

        seq_requests, n_pages = db.db_handler.get_seq_requests(
            limit=PAGE_LIMIT, offset=offset, user_id=user_id, sort_by=sort_by, descending=descending,
            with_statuses=with_statuses, exclude_experiment_id=exclude_experiment_id
        )
        context["user"] = user

    elif (sample_id := request.args.get("sample_id")) is not None:
        template = "components/tables/sample-seq_request.html"
        try:
            sample_id = int(sample_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        if (sample := db.db_handler.get_sample(sample_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if not current_user.is_insider():
            if sample.owner_id != current_user.id:
                return abort(HttpResponse.FORBIDDEN.value.id)
        
        seq_requests, n_pages = db.db_handler.get_seq_requests(
            limit=PAGE_LIMIT, offset=offset, sample_id=sample_id, sort_by=sort_by, descending=descending,
            with_statuses=with_statuses, exclude_experiment_id=exclude_experiment_id
        )
        context["sample"] = sample
    else:
        template = "components/tables/seq_request.html"
        with DBSession(db.db_handler) as session:
            if not current_user.is_insider():
                user_id = current_user.id
            else:
                user_id = None
            seq_requests, n_pages = session.get_seq_requests(
                limit=PAGE_LIMIT, offset=offset, user_id=user_id, sort_by=sort_by, descending=descending,
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
    with DBSession(db.db_handler) as session:
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        samples = seq_request.samples
    
    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HttpResponse.FORBIDDEN.value.id)

    file_name = secure_filename(f"{seq_request.name}_request.xlsx")

    metadata_df = pd.DataFrame.from_records([seq_request.to_dict()]).T
    samples_df = pd.DataFrame.from_records([sample.to_dict() for sample in samples])

    bytes_io = BytesIO()
    with pd.ExcelWriter(bytes_io, engine="openpyxl") as writer:
        metadata_df.to_excel(writer, sheet_name="metadata", index=True)
        samples_df.to_excel(writer, sheet_name="samples", index=False)

    bytes_io.seek(0)
    mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
    return Response(
        bytes_io, mimetype=mimetype,
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )


@seq_requests_htmx.route("<int:seq_request_id>/export_libraries", methods=["GET"])
@login_required
def export_libraries(seq_request_id: int):
    with DBSession(db.db_handler) as session:
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        libraries = seq_request.libraries

    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HttpResponse.FORBIDDEN.value.id)
    
    file_name = secure_filename(f"{seq_request.name}_libraries.tsv")

    df = pd.DataFrame.from_records([library.to_dict() for library in libraries])

    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )


@seq_requests_htmx.route("<int:seq_request_id>/edit", methods=["POST"])
@login_required
def edit(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HttpResponse.FORBIDDEN.value.id)

    seq_request_form = forms.SeqRequestForm()
    validated, seq_request_form = seq_request_form.custom_validate(current_user, seq_request_id=seq_request_id)
    if not validated:
        return make_response(
            render_template(
                "forms/seq_request/seq_request.html",
                seq_request_form=seq_request_form
            ), push_url=False
        )
    
    if (seq_type_raw := seq_request_form.sequencing_type.data) is not None:
        try:
            seq_type = SequencingType.get(int(seq_type_raw))
        except ValueError:
            seq_type = None
    else:
        seq_type = None

    db.db_handler.update_contact(
        seq_request.billing_contact_id,
        name=seq_request_form.billing_contact.data,
        email=seq_request_form.billing_email.data,
        phone=seq_request_form.billing_phone.data,
        address=seq_request_form.billing_address.data,
    )

    db.db_handler.update_contact(
        seq_request.contact_person_id,
        name=seq_request_form.contact_person_name.data,
        phone=seq_request_form.contact_person_phone.data,
        email=seq_request_form.contact_person_email.data,
    )

    if seq_request_form.bioinformatician_name.data:
        if (bioinformatician_contact := seq_request.bioinformatician_contact) is None:
            bioinformatician_contact = db.db_handler.create_contact(
                name=seq_request_form.bioinformatician_name.data,
                email=seq_request_form.bioinformatician_email.data,
                phone=seq_request_form.bioinformatician_phone.data,
            )
        else:
            db.db_handler.update_contact(
                bioinformatician_contact.id,
                name=seq_request_form.bioinformatician_name.data,
                email=seq_request_form.bioinformatician_email.data,
                phone=seq_request_form.bioinformatician_phone.data,
            )

    try:
        flowcell_type_id = int(seq_request_form.flowcell_type.data)
    except ValueError:
        flowcell_type_id = None
    if flowcell_type_id is not None and flowcell_type_id != -1:
        flowcell_type = FlowCellType.get(flowcell_type_id)
    else:
        flowcell_type = None

    if seq_request_form.name.data is not None:
        seq_request.name = seq_request_form.name.data

    if seq_request_form.description.data is not None:
        seq_request.description = seq_request_form.description.data

    if seq_request_form.technology.data is not None:
        seq_request.technology = seq_request_form.technology.data

    if seq_type is not None:
        seq_request.sequencing_type_id = seq_type.value.id

    if seq_request_form.num_cycles_read_1.data is not None:
        seq_request.num_cycles_read_1 = seq_request_form.num_cycles_read_1.data

    if seq_request_form.num_cycles_index_1.data is not None:
        seq_request.num_cycles_index_1 = seq_request_form.num_cycles_index_1.data

    if seq_request_form.num_cycles_index_2.data is not None:
        seq_request.num_cycles_index_2 = seq_request_form.num_cycles_index_2.data

    if seq_request_form.num_cycles_read_2.data is not None:
        seq_request.num_cycles_read_2 = seq_request_form.num_cycles_read_2.data

    if seq_request_form.read_length.data is not None:
        seq_request.read_length = seq_request_form.read_length.data

    if seq_request_form.special_requirements.data is not None:
        seq_request.special_requirements = seq_request_form.special_requirements.data

    if seq_request_form.sequencer.data is not None:
        seq_request.sequencer = seq_request_form.sequencer.data

    if flowcell_type is not None:
        seq_request.flowcell_type_id = flowcell_type.value.id

    if seq_request_form.num_lanes.data is not None:
        seq_request.num_lanes = seq_request_form.num_lanes.data

    if seq_request_form.billing_code.data is not None:
        seq_request.billing_code = seq_request_form.billing_code.data

    if seq_request_form.organization_name.data is not None:
        seq_request.organization_name = seq_request_form.organization_name.data

    if seq_request_form.organization_department.data is not None:
        seq_request.organization_department = seq_request_form.organization_department.data

    if seq_request_form.organization_address.data is not None:
        seq_request.organization_address = seq_request_form.organization_address.data

    seq_request = db.db_handler.update_seq_request(seq_request)

    flash(f"Updated sequencing request '{seq_request.name}'", "success")
    logger.info(f"Updated sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/delete", methods=["DELETE"])
@login_required
def delete(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HttpResponse.FORBIDDEN.value.id)

    db.db_handler.delete_seq_request(seq_request_id)

    flash(f"Deleted sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Deleted sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_requests_page"),
    )


@seq_requests_htmx.route("<int:seq_request_id>/archive", methods=["POST"])
@login_required
def archive(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HttpResponse.FORBIDDEN.value.id)
    
    seq_request.status_id = SeqRequestStatus.ARCHIVED.value.id
    seq_request = db.db_handler.update_seq_request(seq_request)
    flash(f"Archived sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Archived sequencing request '{seq_request.name}'")
    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/unarchive", methods=["POST"])
@login_required
def unarchive(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    seq_request.status_id = SeqRequestStatus.DRAFT.value.id
    seq_request.submitted_time = None
    seq_request = db.db_handler.update_seq_request(seq_request)

    flash(f"Unarchived sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Unarchived sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/edit", methods=["GET"])
@login_required
def submit(seq_request_id: int):
    with DBSession(db.db_handler) as session:
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if seq_request.requestor_id != current_user.id:
            if not current_user.is_insider():
                return abort(HttpResponse.FORBIDDEN.value.id)
        
        if not seq_request.is_submittable():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        session.submit_seq_request(seq_request_id)

    flash(f"Submitted sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Submitted sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("create", methods=["POST"])
@login_required
def create():
    seq_request_form = forms.SeqRequestForm()
    validated, seq_request_form = seq_request_form.custom_validate(current_user)

    if not validated:
        return make_response(
            render_template(
                "forms/seq_request/seq_request.html",
                seq_request_form=seq_request_form
            ), push_url=False
        )

    contact_person = db.db_handler.create_contact(
        name=seq_request_form.contact_person_name.data,
        email=seq_request_form.contact_person_email.data,
        phone=seq_request_form.contact_person_phone.data,
    )

    billing_contact = db.db_handler.create_contact(
        name=seq_request_form.billing_contact.data,
        email=seq_request_form.billing_email.data,
        address=seq_request_form.billing_address.data,
        phone=seq_request_form.billing_phone.data,
    )

    # Create bioinformatician contact if needed
    if seq_request_form.bioinformatician_name.data:
        bioinformatician = db.db_handler.create_contact(
            name=seq_request_form.bioinformatician_name.data,
            email=seq_request_form.bioinformatician_email.data,
            phone=seq_request_form.bioinformatician_phone.data,
        )
        bioinformatician_contact_id = bioinformatician.id
    else:
        bioinformatician_contact_id = None

    if (seq_type_id := seq_request_form.sequencing_type.data) is not None:
        try:
            seq_type = SequencingType.get(int(seq_type_id))
        except ValueError:
            seq_type = SequencingType.OTHER
    else:
        seq_type = SequencingType.OTHER

    if (flowcell_type_id := seq_request_form.flowcell_type.data) is not None:
        try:
            flowcell_type = FlowCellType.get(int(flowcell_type_id))
        except ValueError:
            flowcell_type = None
    else:
        flowcell_type = None

    seq_request = db.db_handler.create_seq_request(
        name=seq_request_form.name.data,
        description=seq_request_form.description.data,
        requestor_id=current_user.id,
        technology=seq_request_form.technology.data,
        contact_person_id=contact_person.id,
        billing_contact_id=billing_contact.id,
        bioinformatician_contact_id=bioinformatician_contact_id,
        seq_type=seq_type,
        num_cycles_read_1=seq_request_form.num_cycles_read_1.data,
        num_cycles_index_1=seq_request_form.num_cycles_index_1.data,
        num_cycles_index_2=seq_request_form.num_cycles_index_2.data,
        num_cycles_read_2=seq_request_form.num_cycles_read_2.data,
        read_length=seq_request_form.read_length.data,
        special_requirements=seq_request_form.special_requirements.data,
        sequencer=seq_request_form.sequencer.data,
        flowcell_type=flowcell_type,
        num_lanes=seq_request_form.num_lanes.data,
        organization_name=seq_request_form.organization_name.data,
        organization_address=seq_request_form.organization_address.data,
        organization_department=seq_request_form.organization_department.data,
    )

    flash(f"Created new sequencing request '{seq_request.name}'", "success")
    logger.info(f"Created new sequencing request '{seq_request.name}'")
    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/upload_auth_form", methods=["POST"])
@login_required
def upload_auth_form(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if seq_request.requestor_id != current_user.id:
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)

    seq_auth_form = forms.SeqAuthForm()
    validated, seq_auth_form = seq_auth_form.custom_validate()
    if not validated:
        return make_response(
            render_template(
                "forms/seq_request/seq_auth.html",
                seq_auth_form=seq_auth_form,
                seq_request=seq_request
            ), push_url=False
        )
    
    uuid = str(uuid4())
    filepath = os.path.join(SEQ_AUTH_FORMS_DIR, f"{uuid}.pdf")
    seq_auth_form.file.data.save(filepath)

    seq_request.seq_auth_form_uuid = uuid
    seq_request = db.db_handler.update_seq_request(seq_request=seq_request)

    flash("Authorization form uploaded!", "success")
    logger.debug(f"Uploaded sequencing authorization form for sequencing request '{seq_request.name}': {uuid}")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/remove_auth_form", methods=["DELETE"])
@login_required
def remove_auth_form(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if seq_request.seq_auth_form_uuid is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if seq_request.requestor_id != current_user.id:
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
    if seq_request.status != SeqRequestStatus.DRAFT:
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)

    filepath = os.path.join(SEQ_AUTH_FORMS_DIR, f"{seq_request.seq_auth_form_uuid}.pdf")
    if os.path.exists(filepath):
        os.remove(filepath)
    seq_request.seq_auth_form_uuid = None
    seq_request = db.db_handler.update_seq_request(seq_request=seq_request)

    flash("Authorization form removed!", "success")
    logger.debug(f"Removed sequencing authorization form for sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/remove_library", methods=["DELETE"])
@login_required
def remove_library(seq_request_id: int):
    if (library_id := request.args.get("library_id")) is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if seq_request.status != SeqRequestStatus.DRAFT:
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
    
    try:
        library_id = int(library_id)
    except ValueError:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if seq_request.requestor_id != current_user.id:
            if not current_user.is_insider():
                return abort(HttpResponse.FORBIDDEN.value.id)
            
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
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if word is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

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
            return abort(HttpResponse.BAD_REQUEST.value.id)
        with DBSession(db.db_handler) as session:
            if (user := session.get_user(user_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            
            seq_requests = __get_seq_requests(session, word, field_name, user_id=user_id)
            context["user"] = user
    else:
        template = "components/tables/seq_request.html"

        with DBSession(db.db_handler) as session:
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
        return abort(HttpResponse.BAD_REQUEST.value.id)
    try:
        index = int(index)
    except ValueError:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    logger.debug(index)
    
    library_id = request.args.get("library_id", None)
    if library_id is not None:
        try:
            library_id = int(library_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if index < 1 or index > 4:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    with DBSession(db.db_handler) as session:
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if seq_request.requestor_id != current_user.id:
            if not current_user.is_insider():
                return abort(HttpResponse.FORBIDDEN.value.id)
            
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


@seq_requests_htmx.route("<int:seq_request_id>/download_pooling_template", methods=["GET"])
@login_required
def download_pooling_template(seq_request_id: int):
    with DBSession(db.db_handler) as session:
        if (_ := session.get_seq_request(seq_request_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        unpooled_libraries, _ = session.get_libraries(seq_request_id=seq_request_id, limit=None)

    unpooled_libraries = [library for library in unpooled_libraries if not library.is_pooled()]
    
    filename = f"pooling_template_{seq_request_id}.tsv"

    data = {
        "id": [],
        "library_name": [],
        "library_type": [],
        "pool": [],
        "index_kit": [],
        "adapter": [],
        "index_1": [],
        "index_2": [],
        "index_3": [],
        "index_4": [],
        "library_volume": [],
        "library_concentration": [],
        "library_total_size": [],
    }
    for library in unpooled_libraries:
        data["id"].append(library.id)
        data["library_name"].append(library.name)
        data["library_type"].append(library.type.value.description)
        data["pool"].append("")
        data["adapter"].append("")
        data["index_1"].append("")
        data["index_2"].append("")
        data["index_3"].append("")
        data["index_4"].append("")
        data["library_volume"].append("")
        data["library_concentration"].append("")
        data["library_total_size"].append("")

    df = pd.DataFrame(data).sort_values(by=["library_type", "library_name"])

    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


@seq_requests_htmx.route("<int:seq_request_id>/pooling_form", methods=["GET"])
@login_required
def pooling_form(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    experiment = None
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            experiment = db.db_handler.get_experiment(experiment_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if seq_request.requestor_id != current_user.id:
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
    
    table_form = forms.TableInputForm("pooling")

    return make_response(
        render_template(
            "components/popups/pooling/pooling-2.html",
            table_form=table_form,
            seq_request=seq_request,
            experiment=experiment,
        ), push_url=False
    )


@seq_requests_htmx.route("<int:seq_request_id>/parse_pooling_form", methods=["POST"])
@login_required
def parse_pooling_form(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    experiment = None
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            experiment = db.db_handler.get_experiment(experiment_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
    pooling_form = forms.PoolingForm()
    validated, table_form, df = pooling_form.custom_validate()

    if not validated or df is None:
        return make_response(
            render_template(
                "components/popups/pooling/pooling-2.html",
                table_form=table_form,
                seq_request=seq_request,
                experiment=experiment,
            )
        )
    
    data = {"pooling_table": df}
    index_kit_mapping_form = forms.IndexKitMappingForm()
    context = index_kit_mapping_form.prepare(data)

    return make_response(
        render_template(
            "components/popups/pooling/pooling-3.html",
            seq_request=seq_request,
            experiment=experiment,
            index_kit_mapping_form=index_kit_mapping_form,
            **context
        )
    )


@seq_requests_htmx.route("<int:seq_request_id>/map_index_kits", methods=["POST"])
@login_required
def map_index_kits(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    experiment = None
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            experiment = db.db_handler.get_experiment(experiment_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
    index_kit_mapping_form = forms.IndexKitMappingForm()
    validated, index_kit_mapping_form = index_kit_mapping_form.custom_validate()
    
    if not validated:
        return make_response(
            render_template(
                "components/popups/pooling/pooling-3.html",
                seq_request=seq_request,
                index_kit_mapping_form=index_kit_mapping_form,
                experiment=experiment,
                **index_kit_mapping_form.prepare()
            )
        )
    
    data = index_kit_mapping_form.parse()
    pool_mapping_form = forms.PoolMappingForm()
    context = pool_mapping_form.prepare(data)

    return make_response(
        render_template(
            "components/popups/pooling/pooling-4.html",
            seq_request=seq_request,
            pool_mapping_form=pool_mapping_form,
            experiment=experiment,
            **context
        )
    )


@seq_requests_htmx.route("<int:seq_request_id>/check_indices", methods=["POST"])
@login_required
def check_indices(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    experiment = None
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            experiment = db.db_handler.get_experiment(experiment_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
    pool_mapping_form = forms.PoolMappingForm()
    validated, pool_mapping_form = pool_mapping_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/pooling/pooling-4.html",
                seq_request=seq_request,
                pool_mapping_form=pool_mapping_form,
                experiment=experiment,
                **pool_mapping_form.prepare()
            )
        )
    
    df = pool_mapping_form.parse()
    
    barcode_check_form = forms.BarcodeCheckForm()
    context = barcode_check_form.prepare(df)

    return make_response(
        render_template(
            "components/popups/pooling/pooling-5.html",
            seq_request=seq_request,
            experiment=experiment,
            pool_mapping_form=pool_mapping_form,
            barcode_check_form=barcode_check_form,
            **context
        ), push_url=False
    )


@seq_requests_htmx.route("<int:seq_request_id>/add_indices", methods=["POST"])
@login_required
def add_indices(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    experiment = None
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            experiment = db.db_handler.get_experiment(experiment_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
    
    barcode_check_form = forms.BarcodeCheckForm()
    valid, barcode_check_form = barcode_check_form.custom_validate()
    if not valid:
        return make_response(
            render_template(
                "components/popups/pooling/pooling-5.html",
                seq_request=seq_request,
                experiment=experiment,
                barcode_check_form=barcode_check_form,
                **barcode_check_form.prepare()
            )
        )

    data = barcode_check_form.parse()
    pooling_table = data["pooling_table"]

    for _, row in pooling_table.iterrows():
        library = db.db_handler.get_library(row["id"])
        library.index_1_sequence = row["index_1"] if not pd.isna(row["index_1"]) else None
        library.index_2_sequence = row["index_2"] if not pd.isna(row["index_2"]) else None
        library.index_3_sequence = row["index_3"] if not pd.isna(row["index_3"]) else None
        library.index_4_sequence = row["index_4"] if not pd.isna(row["index_4"]) else None
        library.adapter = row["adapter"] if not pd.isna(row["adapter"]) else None
        library = db.db_handler.update_library(library)

    n_pools = 0
    for pool_label, _df in pooling_table.groupby("pool"):
        pool_label = str(pool_label)
        logger.debug(pool_label)
        logger.debug(_df[["sample_name", "library_type"]])
        pool = db.db_handler.create_pool(
            name=pool_label,
            owner_id=current_user.id,
            seq_request_id=seq_request_id,
            contact_name=_df["contact_person_name"].iloc[0],
            contact_email=_df["contact_person_email"].iloc[0],
            contact_phone=_df["contact_person_phone"].iloc[0],
        )

        for _, row in _df.iterrows():
            library = db.db_handler.get_library(int(row["id"]))
            library.pool_id = pool.id
            library = db.db_handler.update_library(library)

        n_pools += 1

    if experiment is not None:
        db.db_handler.link_experiment_seq_request(
            experiment_id=experiment.id, seq_request_id=seq_request.id
        )
    
    flash(f"Created and indexed {n_pools} succefully from request '{seq_request.name}'", "success")
    logger.debug(f"Created and indexed {n_pools} succefully from request '{seq_request.name}' [{seq_request.id}]")

    if experiment is not None:
        return make_response(
            redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        )

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/get_graph", methods=["GET"])
@login_required
def get_graph(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if seq_request.requestor_id != current_user.id:
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)

    LINK_WIDTH_UNIT = 1

    with DBSession(db.db_handler) as session:
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
                            "name": link.library.type.value.description,
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
            
        pools, _ = session.get_pools(seq_request_id=seq_request_id, limit=None)

        for pool in pools:
            pool_node = {
                "node": idx,
                "name": pool.name,
                "id": f"pool-{pool.id}"
            }
            graph["nodes"].append(pool_node)
            pool_nodes[pool.id] = idx
            pool_idx = idx
            idx += 1

            link_width = 0
            for library in pool.libraries:
                graph["links"].append({
                    "source": library_nodes[library.id],
                    "target": pool_idx,
                    "value": LINK_WIDTH_UNIT * library.num_samples
                })
                link_width += LINK_WIDTH_UNIT * library.num_samples

            graph["links"].append({
                "source": pool_idx,
                "target": seq_request_node["node"],
                "value": link_width
            })

    return make_response(
        jsonify(graph)
    )