from typing import Optional

from flask import Blueprint, render_template, request, abort, url_for
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, logger, forms
from ....core import DBSession

adapters_htmx = Blueprint("adapters_htmx", __name__, url_prefix="/api/adapters/")

@adapters_htmx.route("<index_kit_id>/get/<int:page>", methods=["GET"], defaults={"index_kit_id": None})
@adapters_htmx.route("<int:index_kit_id>/get/<int:page>", methods=["GET"])
@login_required
def get(page: int, index_kit_id: Optional[int]):
    with DBSession(db.db_handler) as session:
        if index_kit_id is not None:
            index_kit = session.get_index_kit(index_kit_id)
            if index_kit is None:
                return abort(404)

        adapters = session.get_adapters(index_kit_id=index_kit_id, offset=page * 20)
        n_pages = int(session.get_num_adapters(index_kit_id=index_kit_id) / 20)

    return make_response(
        render_template(
            "components/tables/adapter.html", adapters=adapters,
            n_pages=n_pages, active_page=page, index_kit_id=index_kit_id
        ), push_url=False
    )