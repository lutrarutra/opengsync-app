from flask import Blueprint, render_template, abort, url_for
from flask_login import current_user, login_required

from ... import forms, db, logger, PAGE_LIMIT
from ...core import DBSession
from ...categories import UserRole, SeqRequestStatus, HttpResponse

seq_requests_page_bp = Blueprint("seq_requests_page", __name__)


@seq_requests_page_bp.route("/seq_request")
@login_required
def seq_requests_page():
    seq_request_form = forms.SeqRequestForm()
    seq_request_form.contact_person_name.data = f"{current_user.first_name} {current_user.last_name}"
    seq_request_form.contact_person_email.data = current_user.email

    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            seq_requests, n_pages = session.get_seq_requests(limit=PAGE_LIMIT, user_id=current_user.id)
        elif current_user.role_type == UserRole.ADMIN:
            seq_requests, n_pages = session.get_seq_requests(limit=PAGE_LIMIT, user_id=None)
        else:
            seq_requests, n_pages = session.get_seq_requests(limit=PAGE_LIMIT, user_id=None, show_drafts=False)

    return render_template(
        "seq_requests_page.html",
        seq_request_form=seq_request_form,
        seq_requests=seq_requests,
        n_pages=n_pages, active_page=0,
        current_sort="id", current_sort_order="desc"
    )


@seq_requests_page_bp.route("/seq_request/<int:seq_request_id>")
@login_required
def seq_request_page(seq_request_id: int):
    with DBSession(db.db_handler) as session:
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        if seq_request.requestor_id != current_user.id:
            if not current_user.is_insider():
                return abort(HttpResponse.FORBIDDEN.value.id)
            
        libraries = seq_request.libraries

    if not current_user.is_insider():
        if seq_request.requestor_id != current_user.id:
            return abort(HttpResponse.FORBIDDEN.value.id)

    seq_request_form = forms.SeqRequestForm()
    seq_request_form.current_user_is_contact.data = False
    seq_request_form.billing_is_organization.data = False

    seq_request_form.name.data = seq_request.name
    seq_request_form.description.data = seq_request.description

    seq_request_form.contact_person_name.data = seq_request.contact_person.name
    seq_request_form.contact_person_email.data = seq_request.contact_person.email
    seq_request_form.contact_person_phone.data = seq_request.contact_person.phone

    organization_name = seq_request.contact_person.organization
    if " (" in organization_name:
        organization_name = organization_name.split(" (")[0]
        seq_request_form.organization_department.data = seq_request.contact_person.organization.split(" (")[1][:-1]

    seq_request_form.organization_name.data = organization_name
    seq_request_form.organization_address.data = seq_request.contact_person.address

    if seq_request.bioinformatician_contact is not None:
        seq_request_form.bioinformatician_name.data = seq_request.bioinformatician_contact.name
        seq_request_form.bioinformatician_email.data = seq_request.bioinformatician_contact.email
        seq_request_form.bioinformatician_phone.data = seq_request.bioinformatician_contact.phone

    if seq_request.library_person_contact is not None:
        seq_request_form.library_contact_name.data = seq_request.library_person_contact.name
        seq_request_form.library_contact_email.data = seq_request.library_person_contact.email
        seq_request_form.library_contact_phone.data = seq_request.library_person_contact.phone

    seq_request_form.billing_contact.data = seq_request.billing_contact.name
    seq_request_form.billing_address.data = seq_request.billing_contact.address
    seq_request_form.billing_email.data = seq_request.billing_contact.email
    seq_request_form.billing_phone.data = seq_request.billing_contact.phone
    seq_request_form.billing_code.data = seq_request.billing_contact.billing_code

    library_results, _ = db.db_handler.get_libraries(user_id=current_user.id)

    path_list = [
        ("Requests", url_for("seq_requests_page.seq_requests_page")),
        (f"{seq_request_id}", ""),
    ]

    return render_template(
        "seq_request_page.html",
        seq_request=seq_request,
        libraries=libraries,
        path_list=path_list,
        select_library_form=forms.SelectLibraryForm(),
        library_results=library_results,
        seq_request_form=seq_request_form
    )
