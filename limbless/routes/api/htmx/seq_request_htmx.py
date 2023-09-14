from flask import Blueprint, url_for, render_template, flash
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, forms, logger
from ....core import DBSession

seq_requests_htmx = Blueprint("seq_requests_htmx", __name__, url_prefix="/api/seq_requests/")


@login_required
@seq_requests_htmx.route("create", methods=["POST"])
def create():
    seq_request_form = forms.SeqRequestForm()

    if not seq_request_form.validate_on_submit():
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

    seq_request = db.db_handler.create_seq_request(
        name=seq_request_form.name.data,
        description=seq_request_form.description.data,
        requestor_id=current_user.id,
        person_contact_id=contact_person.id,
        billing_contact_id=billing_contact.id,
    )        

    flash(f"Created new sequencing request '{seq_request.name}'")
    logger.info(f"Created new sequencing request '{seq_request.name}'")
    return make_response(
        
