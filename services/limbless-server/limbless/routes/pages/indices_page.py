from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import current_user, login_required

from ... import forms, models, db, logger, PAGE_LIMIT
from ...core import DBSession

index_kit_page_bp = Blueprint("index_kit_page", __name__)


@login_required
@index_kit_page_bp.route("/index_kit")
def index_kit_page():
    with DBSession(db.db_handler) as session:
        index_kit, n_pages = session.get_index_kits(limit=PAGE_LIMIT)

    logger.debug(index_kit)

    return render_template(
        "index_kit_page.html",
        index_kit=index_kit, index_kits_n_pages=n_pages, index_kits_active_page=0,
    )