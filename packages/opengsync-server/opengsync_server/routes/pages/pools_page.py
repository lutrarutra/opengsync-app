from flask import Blueprint, render_template, url_for, request

from opengsync_db.categories import PoolStatus, AccessLevel
from opengsync_db import models, queries as Q

from ... import db
from ...core import wrappers, exceptions
pools_page_bp = Blueprint("pools_page", __name__)


@wrappers.page_route(pools_page_bp, db=db, cache_timeout_seconds=360)
def pools():
    return render_template("pools_page.html", title="Pools")


@wrappers.page_route(pools_page_bp, "pools", db=db, cache_timeout_seconds=360)
def pool(current_user: models.User, pool_id: int):
    if (pool := db.session.first(Q.pool.select(id=pool_id))) is None:
        raise exceptions.NotFoundException()
    
    if db.session.get_access_level(Q.pool.permissions(pool.id, current_user.id)) < AccessLevel.READ:
         raise exceptions.NoPermissionsException()

    path_list = [
        ("Pools", url_for("pool_pages")),
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
                ("Requests", url_for("seq_request_pages")),
                (f"Request {id}", url_for("seq_request_page", seq_request_id=id)),
                (f"Pool {pool_id}", ""),
            ]
        elif page == "lab_prep":
            path_list = [
                ("Lab Preps", url_for("lab_preps_page.lab_preps")),
                (f"Lab Prep {id}", url_for("lab_preps_page.lab_prep", lab_prep_id=id)),
                (f"Pool {pool_id}", ""),
            ]

    is_editable = pool.status == PoolStatus.DRAFT or current_user.is_insider
    is_indexed = True and len(pool.libraries) > 0
    for library in pool.libraries:
        if not library.is_indexed:
            is_indexed = False
            break

    return render_template(
        "pool_page.html", pool=pool, path_list=path_list, is_editable=is_editable,
        is_plated=False, is_indexed=is_indexed, title=f"Pool: {pool.name}"
    )
