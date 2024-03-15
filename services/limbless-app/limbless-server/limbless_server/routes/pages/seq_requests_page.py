from typing import TYPE_CHECKING

from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import UserRole, HTTPResponse
from ... import forms, db, logger

seq_requests_page_bp = Blueprint("seq_requests_page", __name__)

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user


@seq_requests_page_bp.route("/seq_requests")
@login_required
def seq_requests_page():
    seq_request_form = forms.SeqRequestForm()
    seq_request_form.contact_person_name.data = current_user.name
    seq_request_form.contact_person_email.data = current_user.email

    current_sort = "id"

    with DBSession(db) as session:
        if not current_user.is_insider():
            seq_requests, n_pages = session.get_seq_requests(user_id=current_user.id)
        elif current_user.role == UserRole.ADMIN:
            seq_requests, n_pages = session.get_seq_requests(user_id=None)
        else:
            seq_requests, n_pages = session.get_seq_requests(user_id=None, show_drafts=False, sort_by=current_sort, descending=True)

    open_form = request.args.get("open_form") is not None

    return render_template(
        "seq_requests_page.html",
        seq_request_form=seq_request_form,
        seq_requests=seq_requests,
        open_form=open_form,
        seq_requests_n_pages=n_pages, seq_requests_active_page=0,
        seq_requests_current_sort=current_sort, seq_requests_current_sort_order="desc"
    )


@seq_requests_page_bp.route("/seq_requests/<int:seq_request_id>")
@login_required
def seq_request_page(seq_request_id: int):
    with DBSession(db) as session:
        if (seq_request := session.get_seq_request(seq_request_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        if seq_request.requestor_id != current_user.id:
            if not current_user.is_insider():
                return abort(HTTPResponse.FORBIDDEN.id)
            
        libraries, libraries_n_pages = session.get_libraries(seq_request_id=seq_request_id, sort_by="id", descending=True)
        samples, samples_n_pages = session.get_samples(seq_request_id=seq_request_id, sort_by="id", descending=True)

        if not current_user.is_insider():
            if seq_request.requestor_id != current_user.id:
                return abort(HTTPResponse.FORBIDDEN.id)

        seq_request_form = forms.SeqRequestForm(seq_request=seq_request)

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

        process_request_form = forms.ProcessRequestForm(seq_request=seq_request)
        seq_auth_form = forms.SeqAuthForm()
        file_input_form = forms.SeqRequestAttachmentForm(seq_request_id=seq_request_id)
        comment_form = forms.SeqRequestCommentForm(seq_request_id=seq_request_id)
        seq_request_share_email_form = forms.SeqRequestShareEmailForm()

        return render_template(
            "seq_request_page.html",
            seq_request=seq_request,
            libraries=libraries,
            samples=samples,
            path_list=path_list,
            comment_form=comment_form,
            library_results=library_results,
            seq_request_share_email_form=seq_request_share_email_form,
            seq_request_form=seq_request_form,
            file_input_form=file_input_form,
            process_request_form=process_request_form,
            seq_auth_form=seq_auth_form,
            libraries_n_pages=libraries_n_pages, libraries_active_page=0,
            samples_n_pages=samples_n_pages, samples_active_page=0,
        )
