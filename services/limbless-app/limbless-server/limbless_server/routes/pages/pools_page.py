from typing import TYPE_CHECKING

from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required

from limbless_db import db_session
from limbless_db.categories import PoolStatus
from limbless_db.models import User
from limbless_db.categories import HTTPResponse

from ... import db

if TYPE_CHECKING:
    current_user: User = None  # type: ignore
else:
    from flask_login import current_user

pools_page_bp = Blueprint("pools_page", __name__)


@pools_page_bp.route("/pools")
@login_required
def pools_page():
    return render_template("pools_page.html")


@pools_page_bp.route("/pools/<int:pool_id>")
@db_session(db)
@login_required
def pool_page(pool_id: int):
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and pool.owner_id != current_user.id:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    pool.contact

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

    is_editable = pool.status == PoolStatus.DRAFT or current_user.is_insider()
    is_plated = True and len(pool.libraries) > 0
    is_indexed = True and len(pool.libraries) > 0
    for library in pool.libraries:
        if library.plate_id is None:
            is_plated = False
        if not library.is_indexed():
            is_indexed = False

    return render_template(
        "pool_page.html", pool=pool, path_list=path_list, is_editable=is_editable,
        is_plated=is_plated, is_indexed=is_indexed
    )
