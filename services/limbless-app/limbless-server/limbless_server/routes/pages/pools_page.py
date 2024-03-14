from typing import TYPE_CHECKING

from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required

from limbless_db import DBSession
from limbless_db.models import User
from limbless_db.categories import HTTPResponse

from ...app import db
from ...forms import pooling as pooling_forms

if TYPE_CHECKING:
    current_user: User = None  # type: ignore
else:
    from flask_login import current_user

pools_page_bp = Blueprint("pools_page", __name__)


@pools_page_bp.route("/pools")
@login_required
def pools_page():
    with DBSession(db) as session:
        if not current_user.is_insider():
            pools, n_pages = session.get_pools(user_id=current_user.id, sort_by="id", descending=True)
        else:
            pools, n_pages = session.get_pools(user_id=None, sort_by="id", descending=True)

    return render_template(
        "pools_page.html",
        pools=pools,
        index_kit_results=[],
        pools_n_pages=n_pages, pools_active_page=0,
        current_sort="id", current_sort_order="desc"
    )


@pools_page_bp.route("/pools/<int:pool_id>")
@login_required
def pool_page(pool_id: int):
    with DBSession(db) as session:
        if (pool := session.get_pool(pool_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if not current_user.is_insider() and pool.owner_id != current_user.id:
            return abort(HTTPResponse.FORBIDDEN.id)

        libraries, libraries_n_pages = session.get_libraries(pool_id=pool_id, sort_by="id", descending=True)
        is_editable = pool.is_editable()

        path_list = [
            ("Pools", url_for("pools_page.pools_page")),
            (f"Pool {pool.id}", ""),
        ]
        if (_from := request.args.get("from", None)) is not None:
            page, id = _from.split("@")
            if page == "experiment":
                path_list = [
                    ("Experiments", url_for("experiments_page.experiments_page")),
                    (f"Experiment {id}", url_for("experiments_page.experiment_page", experiment_id=id)),
                    (f"Pool {pool_id}", ""),
                ]

        open_index_form = request.args.get("index_form", None) == "open"
        pooling_input_form = pooling_forms.PoolingInputForm()

        return render_template(
            "pool_page.html",
            pool=pool, libraries=libraries,
            libraries_n_pages=libraries_n_pages,
            libraries_active_page=0,
            libraries_current_sort="id",
            libraries_current_sort_order="desc",
            path_list=path_list, is_editable=is_editable,
            open_index_form=open_index_form,
            pooling_input_form=pooling_input_form
        )
