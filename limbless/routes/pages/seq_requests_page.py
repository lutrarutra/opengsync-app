from typing import TYPE_CHECKING

from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required

from ... import forms, db, logger, PAGE_LIMIT, models
from ...core import DBSession
from ...categories import UserRole, HttpResponse

seq_requests_page_bp = Blueprint("seq_requests_page", __name__)

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user


@seq_requests_page_bp.route("/seq_request")
@login_required
def seq_requests_page():
    seq_request_form = forms.SeqRequestForm()
    seq_request_form.contact_person_name.data = current_user.name
    seq_request_form.contact_person_email.data = current_user.email

    current_sort = "id"

    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            seq_requests, n_pages = session.get_seq_requests(limit=PAGE_LIMIT, user_id=current_user.id)
        elif current_user.role_type == UserRole.ADMIN:
            seq_requests, n_pages = session.get_seq_requests(limit=PAGE_LIMIT, user_id=None)
        else:
            seq_requests, n_pages = session.get_seq_requests(limit=PAGE_LIMIT, user_id=None, show_drafts=False, sort_by=current_sort, descending=True)

    return render_template(
        "seq_requests_page.html",
        seq_request_form=seq_request_form,
        seq_requests=seq_requests,
        seq_requests_n_pages=n_pages, seq_requests_active_page=0,
        seq_requests_current_sort=current_sort, seq_requests_current_sort_order="desc"
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
            
        libraries, libraries_n_pages = session.get_libraries(seq_request_id=seq_request_id, sort_by="id", descending=True)
        samples, samples_n_pages = session.get_samples(seq_request_id=seq_request_id, sort_by="id", descending=True)

        if not current_user.is_insider():
            if seq_request.requestor_id != current_user.id:
                return abort(HttpResponse.FORBIDDEN.value.id)

        seq_request_form = forms.SeqRequestForm(
            current_user_is_contact=False,
            billing_is_organization=False,

            name=seq_request.name,
            description=seq_request.description,

            num_cycles_read_1=seq_request.num_cycles_read_1,
            num_cycles_index_1=seq_request.num_cycles_index_1,
            num_cycles_index_2=seq_request.num_cycles_index_2,
            num_cycles_read_2=seq_request.num_cycles_read_2,
            read_length=seq_request.read_length,
            num_lanes=seq_request.num_lanes,
            special_requirements=seq_request.special_requirements,
            sequencer=seq_request.sequencer,
            sequencing_type=seq_request.sequencing_type.value.id,

            contact_person_name=seq_request.contact_person.name,
            contact_person_email=seq_request.contact_person.email,
            contact_person_phone=seq_request.contact_person.phone,

            organization_name=seq_request.organization_name,
            organization_department=seq_request.organization_department,
            organization_address=seq_request.organization_address,

            billing_contact=seq_request.billing_contact.name,
            billing_email=seq_request.billing_contact.email,
            billing_phone=seq_request.billing_contact.phone,
            billing_address=seq_request.billing_contact.address,
            billing_code=seq_request.billing_code,

            bioinformatician_name=seq_request.bioinformatician_contact.name if seq_request.bioinformatician_contact is not None else None,
            bioinformatician_email=seq_request.bioinformatician_contact.email if seq_request.bioinformatician_contact is not None else None,
            bioinformatician_phone=seq_request.bioinformatician_contact.phone if seq_request.bioinformatician_contact is not None else None,
        )

        library_results = []

        path_list = [
            ("Requests", url_for("seq_requests_page.seq_requests_page")),
            (f"Request {seq_request_id}", ""),
        ]
        if (_from := request.args.get("from")) is not None:
            page, id = _from.split("@")
            if page == "experiment":
                path_list = [
                    ("Experiments", url_for("experiments_page.experiments_page")),
                    (f"Experiment {id}", url_for("experiments_page.experiment_page", experiment_id=id)),
                    (f"Request {seq_request_id}", ""),
                ]

        return render_template(
            "seq_request_page.html",
            seq_request=seq_request,
            libraries=libraries,
            samples=samples,
            path_list=path_list,
            library_results=library_results,
            seq_request_form=seq_request_form,
            table_form=forms.TableForm(),
            libraries_n_pages=libraries_n_pages, libraries_active_page=0,
            samples_n_pages=samples_n_pages, samples_active_page=0,
        )
