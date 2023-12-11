from io import StringIO, BytesIO
from typing import Optional, TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, abort, request, Response
from flask_htmx import make_response
from flask_login import login_required
from werkzeug.utils import secure_filename
import pandas as pd

from .... import db, forms, logger, models, PAGE_LIMIT, tools
from ....core import DBSession, DBHandler
from ....categories import UserRole, SeqRequestStatus, HttpResponse, SequencingType

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

        seq_requests, n_pages = db.db_handler.get_seq_requests(limit=PAGE_LIMIT, offset=offset, user_id=user_id, sort_by=sort_by, descending=descending)
        context["user"] = user

    if (sample_id := request.args.get("sample_id")) is not None:
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
        
        seq_requests, n_pages = db.db_handler.get_seq_requests(limit=PAGE_LIMIT, offset=offset, sample_id=sample_id, sort_by=sort_by, descending=descending)
        context["sample"] = sample
    else:
        template = "components/tables/seq_request.html"
        with DBSession(db.db_handler) as session:
            if not current_user.is_insider():
                user_id = current_user.id
            else:
                user_id = None
            seq_requests, n_pages = session.get_seq_requests(limit=PAGE_LIMIT, offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, show_drafts=True)

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
    validated, seq_request_form = seq_request_form.custom_validate()
    if not validated:
        logger.debug(seq_request_form.errors)
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

    logger.debug(seq_type)

    db.db_handler.update_contact(
        seq_request.billing_contact_id,
        name=seq_request_form.billing_contact.data,
        email=seq_request_form.billing_email.data,
        phone=seq_request_form.billing_phone.data,
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

    db.db_handler.update_seq_request(
        seq_request_id,
        name=seq_request_form.name.data,
        description=seq_request_form.description.data,
        seq_type=seq_type,
        num_cycles_read_1=seq_request_form.num_cycles_read_1.data,
        num_cycles_index_1=seq_request_form.num_cycles_index_1.data,
        num_cycles_index_2=seq_request_form.num_cycles_index_2.data,
        num_cycles_read_2=seq_request_form.num_cycles_read_2.data,
        read_length=seq_request_form.read_length.data,
        special_requirements=seq_request_form.special_requirements.data,
        sequencer=seq_request_form.sequencer.data,
        num_lanes=seq_request_form.num_lanes.data,
        billing_code=seq_request_form.billing_code.data,
    )

    flash(f"Updated sequencing request '{seq_request.name}'", "success")
    logger.info(f"Updated sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/delete", methods=["GET"])
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
    validated, seq_request_form = seq_request_form.custom_validate()

    if not validated:
        logger.debug(seq_request_form.sequencing_type.data)

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

    seq_request = db.db_handler.create_seq_request(
        name=seq_request_form.name.data,
        description=seq_request_form.description.data,
        requestor_id=current_user.id,
        contact_person_id=contact_person.id,
        billing_contact_id=billing_contact.id,
        bioinformatician_contact_id=bioinformatician_contact_id,
        seq_type=seq_request_form.sequencing_type.data,
        num_cycles_read_1=seq_request_form.num_cycles_read_1.data,
        num_cycles_index_1=seq_request_form.num_cycles_index_1.data,
        num_cycles_index_2=seq_request_form.num_cycles_index_2.data,
        num_cycles_read_2=seq_request_form.num_cycles_read_2.data,
        read_length=seq_request_form.read_length.data,
        special_requirements=seq_request_form.special_requirements.data,
        sequencer=seq_request_form.sequencer.data,
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


@seq_requests_htmx.route("<int:seq_request_id>/remove_library", methods=["DELETE"])
@login_required
def remove_library(seq_request_id: int):
    if (library_id := request.args.get("library_id")) is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    try:
        library_id = int(library_id)
    except ValueError:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if seq_request.requestor_id != current_user.id:
            if not current_user.is_insider():
                return abort(HttpResponse.FORBIDDEN.value.id)
            
        session.unlink_library_seq_request(
            library_id=library_id, seq_request_id=seq_request_id
        )

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
    
    library_id = request.args.get("library_id", None)
    if library_id is not None:
        try:
            library_id = int(library_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
    logger.debug(library_id)
    logger.debug(index)
    
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
            for barcode in library.barcodes:
                if index == barcode.type.value.id:
                    barcode = session.reverse_complement(barcode.id)
                    n_barcodes += 1

    flash(f"Reverse complemented index {index} of sequencing request '{seq_request.name}' in {n_barcodes} libraries.", "success")
    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request_id),
    )