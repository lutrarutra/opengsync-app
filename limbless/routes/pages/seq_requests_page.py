from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user, login_required

from ... import forms

seq_requests_page_bp = Blueprint("seq_requests_page", __name__)


@seq_requests_page_bp.route("/seq_request")
@login_required
def seq_requests_page():
    seq_request_form = forms.SeqRequestForm()
    return render_template(
        "seq_requests_page.html",
        seq_request_form=seq_request_form
    )

# @seq_requests_page_bp.route("/seq_request")
# def seq_requests_page():
#     return render_template(
#         "seq_requests_page.html"
#     )
