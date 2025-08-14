from flask import Blueprint, render_template, abort, url_for, request

from opengsync_db.categories import PoolStatus
from opengsync_db import models
from opengsync_db.categories import HTTPResponse

from ... import db
from ...core import wrappers
pools_page_bp = Blueprint("pools_page", __name__)


@wrappers.page_route(pools_page_bp, db=db)
def pools():
    return render_template("pools_page.html")


@wrappers.page_route(pools_page_bp, db=db)
def pool(current_user: models.User, pool_id: int):
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and pool.owner_id != current_user.id:
        return abort(HTTPResponse.FORBIDDEN.id)

    path_list = [
        ("Pools", url_for("pools_page.pools")),
        (f"Pool {pool.id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "experiment":
            path_list = [
                ("Experiments", url_for("experiments_page.experiments")),
                (f"Experiment {id}", url_for("experiments_page.experiment", experiment_id=id)),
                (f"Pool {pool_id}", ""),
            ]
        elif page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries")),
                (f"Library {id}", url_for("libraries_page.library", library_id=id)),
                (f"Pool {pool_id}", ""),
            ]
        elif page == "seq_request":
            path_list = [
                ("Requests", url_for("seq_requests_page.seq_requests")),
                (f"Request {id}", url_for("seq_requests_page.seq_request", seq_request_id=id)),
                (f"Pool {pool_id}", ""),
            ]
        elif page == "lab_prep":
            path_list = [
                ("Lab Preps", url_for("lab_preps_page.lab_preps")),
                (f"Lab Prep {id}", url_for("lab_preps_page.lab_prep", lab_prep_id=id)),
                (f"Pool {pool_id}", ""),
            ]

    is_editable = pool.status == PoolStatus.DRAFT or current_user.is_insider()
    is_indexed = True and len(pool.libraries) > 0
    for library in pool.libraries:
        if not library.is_indexed():
            is_indexed = False
            break

    return render_template(
        "pool_page.html", pool=pool, path_list=path_list, is_editable=is_editable,
        is_plated=False, is_indexed=is_indexed
    )
