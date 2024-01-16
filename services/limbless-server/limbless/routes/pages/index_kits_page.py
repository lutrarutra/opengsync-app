from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import current_user, login_required

from ... import forms, models, db, logger, PAGE_LIMIT
from ...core import DBSession

index_kits_page_bp = Blueprint("index_kits_page", __name__)


@index_kits_page_bp.route("/index_kit")
@login_required
def index_kits_page():
    with DBSession(db.db_handler) as session:
        index_kits, n_pages = session.get_index_kits(limit=PAGE_LIMIT)

    return render_template(
        "index_kits_page.html",
        index_kits=index_kits, index_kits_n_pages=n_pages, index_kits_active_page=0,
        
    )


@index_kits_page_bp.route("/index_kit/<int:index_kit_id>")
@login_required
def index_kit_page(index_kit_id: int):
    with DBSession(db.db_handler) as session:
        index_kit = session.get_index_kit(index_kit_id)

    path_list = [
        ("Index Kits", url_for("index_kits_page.index_kits_page")),
        (f"{index_kit_id}", ""),
    ]

    adapters, adapters_n_pages = session.get_adapters(index_kit_id=index_kit_id, limit=PAGE_LIMIT)

    return render_template(
        "index_kit_page.html",
        path_list=path_list,
        index_kit=index_kit,
        adapters=adapters,
        adapters_n_pages=adapters_n_pages,
        adapters_active_page=0,
    )