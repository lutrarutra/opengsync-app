from typing import TYPE_CHECKING

from flask import Blueprint, render_template, url_for, abort
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse, FileType

from ... import forms, db, logger  # noqa

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

seq_runs_page_bp = Blueprint("seq_runs_page", __name__)


@seq_runs_page_bp.route("/seq_runs")
@login_required
def seq_runs_page():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    return render_template("seq_runs_page.html")