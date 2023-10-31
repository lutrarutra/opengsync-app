from typing import Optional

from flask import Blueprint, url_for, render_template, flash, abort, request
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, forms, logger, models
from ....core import DBSession, DBHandler
from ....categories import UserRole, SeqRequestStatus, HttpResponse

seq_requests_htmx = Blueprint("seq_requests_htmx", __name__, url_prefix="/api/seq_requests/")


@seq_requests_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    reversed = order == "desc"
    offset = 20 * page

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
        
        if user_id != current_user.id and current_user.role_type not in UserRole.insiders:
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        if (user := db.db_handler.get_user(user_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)

        seq_requests, n_pages = db.db_handler.get_seq_requests(limit=20, offset=offset, user_id=user_id, sort_by=sort_by, reversed=reversed)
        context["user"] = user
    else:
        template = "components/tables/seq_request.html"
        with DBSession(db.db_handler) as session:
            if current_user.role_type not in UserRole.insiders:
                user_id = current_user.id
            else:
                user_id = None
            seq_requests, n_pages = session.get_seq_requests(limit=20, offset=offset, user_id=user_id, sort_by=sort_by, reversed=reversed)

    return make_response(
        render_template(
            template, seq_requests=seq_requests,
            n_pages=n_pages, active_page=page,
            current_sort=sort_by, current_sort_order=order,
            **context
        ), push_url=False
    )


@seq_requests_htmx.route("<int:seq_request_id>/edit", methods=["POST"])
@login_required
def edit(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    if current_user.role_type == UserRole.CLIENT:
        if seq_request.requestor_id != current_user.id:
            return abort(HttpResponse.FORBIDDEN.value.id)

    seq_request_form = forms.SeqRequestForm()
    db.db_handler.update_seq_request(
        seq_request_id,
        name=seq_request_form.name.data,
        description=seq_request_form.description.data,
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

    if current_user.role_type == UserRole.CLIENT:
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
            if seq_request.requestor.role_type not in [UserRole.ADMIN]:
                return abort(HttpResponse.FORBIDDEN.value.id)
        
        if seq_request.status_type != SeqRequestStatus.DRAFT:
            logger.debug(seq_request.status_type)
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        if len(seq_request.libraries) == 0:
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        session.update_seq_request(
            seq_request_id=seq_request_id,
            status=SeqRequestStatus.SUBMITTED,
        )

    flash(f"Submitted sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Submitted sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("create", methods=["POST"])
@login_required
def create():
    seq_request_form = forms.SeqRequestForm()

    if not seq_request_form.validate_on_submit():
        if seq_request_form.bioinformatician_name.data:
            if not seq_request_form.bioinformatician_email.data:
                seq_request_form.bioinformatician_email.errors.append("Bioinformatician email is required")
                seq_request_form.bioinformatician_email.flags.required = True
        template = render_template(
            "forms/seq_request/seq_request.html",
            seq_request_form=seq_request_form
        )
        return make_response(
            template, push_url=False
        )

    organization_name = seq_request_form.organization_name.data
    if seq_request_form.organization_department.data:
        organization_name += f" ({seq_request_form.organization_department.data})"

    contact_person = db.db_handler.create_contact(
        name=seq_request_form.contact_person_name.data,
        organization=organization_name,
        email=seq_request_form.contact_person_email.data,
        phone=seq_request_form.contact_person_phone.data,
        address=seq_request_form.organization_address.data,
    )

    billing_contact = db.db_handler.create_contact(
        name=seq_request_form.billing_contact.data,
        address=seq_request_form.billing_address.data,
        email=seq_request_form.billing_email.data,
        phone=seq_request_form.billing_phone.data,
        billing_code=seq_request_form.billing_code.data
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

    # Create library person contact if needed
    if seq_request_form.library_contact_name.data:
        library_person = db.db_handler.create_contact(
            name=seq_request_form.library_contact_name.data,
            email=seq_request_form.library_contact_email.data,
            phone=seq_request_form.library_contact_phone.data,
        )
        library_person_id = library_person.id
    else:
        library_person_id = None

    seq_request = db.db_handler.create_seq_request(
        name=seq_request_form.name.data,
        description=seq_request_form.description.data,
        requestor_id=current_user.id,
        person_contact_id=contact_person.id,
        billing_contact_id=billing_contact.id,
        bioinformatician_contact_id=bioinformatician_contact_id,
        library_person_contact_id=library_person_id,
    )

    flash(f"Created new sequencing request '{seq_request.name}'", "success")
    logger.info(f"Created new sequencing request '{seq_request.name}'")
    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
    )


@seq_requests_htmx.route("<int:seq_request_id>/add_library", methods=["POST"])
@login_required
def add_library(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    if seq_request.requestor_id != current_user.id:
        if current_user.role_type != UserRole.ADMIN:
            return abort(HttpResponse.FORBIDDEN.value.id)

    select_library_form = forms.SelectLibraryForm()

    if not select_library_form.validate_on_submit():
        template = render_template(
            "forms/seq_request/select_library.html",
            select_library_form=select_library_form
        )
        return make_response(
            template, push_url=False
        )
    
    library_id = select_library_form.library.data
    if (library := db.db_handler.get_library(library_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    _ = db.db_handler.link_library_seq_request(library_id, seq_request_id)

    flash(f"Added library '{library.name}' to sequencing request '{seq_request.name}'", "success")
    logger.debug(f"Added library '{library.name}' to sequencing request '{seq_request.name}'")

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request_id),
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
            if current_user.role_type not in UserRole.insiders:
                return abort(HttpResponse.FORBIDDEN.value.id)
            
        session.unlink_library_seq_request(library_id, seq_request_id)

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
            if current_user.role_type not in UserRole.insiders:
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
        
