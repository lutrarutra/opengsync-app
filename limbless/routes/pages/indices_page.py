from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import current_user, login_required

from ... import forms, models, db, logger
from ...core import DBSession

index_kit_page_bp = Blueprint("index_kit_page", __name__)


@login_required
@index_kit_page_bp.route("/index_kit")
def index_kit_page():
    with DBSession(db.db_handler) as session:
        index_kit = session.get_index_kits(limit=20)
        n_pages = int(session.get_num_index_kits() / 20)

    logger.debug(index_kit)

    return render_template(
        "index_kit_page.html",
        index_kit=index_kit, n_pages=n_pages, active_page=0,
    )