from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import current_user, login_required

from ... import forms, models, db, logger
from ...core import DBSession

indices_page_bp = Blueprint("indices_page", __name__)


@login_required
@indices_page_bp.route("/indices")
def indices_page():
    with DBSession(db.db_handler) as session:
        indices = session.get_seqindices(limit=20)
        n_pages = int(session.get_num_seqindices() / 20)

    logger.debug(indices)

    return render_template(
        "indices_page.html",
        indices=indices, n_pages=n_pages, active_page=0,
    )