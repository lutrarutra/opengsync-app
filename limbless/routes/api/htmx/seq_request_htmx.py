from flask import Blueprint, url_for, render_template, flash
from flask_htmx import make_response
from flask_login import login_required

from .... import db, forms, logger

seq_requests_htmx = Blueprint("seq_requests_htmx", __name__, url_prefix="/api/seq_requests/")


@login_required
@seq_requests_htmx.route("create", methods=["POST"])
def create():
    seq_request_form = forms.SeqRequestForm()

    if not seq_request_form.validate_on_submit():
        template = render_template(
            "forms/seq_request.html",
            seq_request_form=seq_request_form
        )
        return make_response(
            template, push_url=False
        )
