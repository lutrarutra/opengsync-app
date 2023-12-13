from typing import Optional, TYPE_CHECKING
from io import StringIO

import pandas as pd
from flask import Blueprint, redirect, url_for, render_template, flash, request, abort, Response
from flask_htmx import make_response
from flask_login import login_required

from .... import db, logger, forms, models, tools, PAGE_LIMIT
from ....core import DBSession, exceptions
from ....core.DBHandler import DBHandler
from ....categories import UserRole, HttpResponse, LibraryType

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user

pools_htmx = Blueprint("pools_htmx", __name__, url_prefix="/api/pools/")


@pools_htmx.route("get", methods=["POST"])
@login_required
def get(page):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    pools: list[models.Pool] = []
    context = {}
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        template = "components/tables/experiment-pool.html"
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        with DBSession(db.db_handler) as session:
            if (experiment := session.get_experiment(experiment_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            access = session.get_user_experiment_access(current_user.id, experiment_id)
            if access is None:
                return abort(HttpResponse.FORBIDDEN.value.id)
            
            pools, n_pages = session.get_pools(
                experiment_id=experiment_id, sort_by=sort_by, descending=descending,
                offset=offset, limit=PAGE_LIMIT
            )
            context["experiment"] = experiment

    else:
        template = "components/tables/pool.html"
        with DBSession(db.db_handler) as session:
            pools, n_pages = session.get_pools(
                sort_by=sort_by, descending=descending,
                offset=offset, limit=PAGE_LIMIT
            )

    return make_response(
        render_template(
            template, pools=pools, pools_n_pages=n_pages,
            pools_active_page=page, **context
        )
    )


@pools_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    abort(404)


@pools_htmx.route("<int:pool_id>/download_template", methods=["GET"])
@login_required
def download_template(pool_id: int):
    with DBSession(db.db_handler) as session:
        if (pool := session.get_pool(pool_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        libraries = pool.libraries
    
    filename = f"pool_index_{pool.id}.tsv"

    data = {
        "library_id": [],
        "library_name": [],
        "library_type": [],
        "adapter": [],
        "index_1": [],
        "index_2": [],
        "index_3": [],
        "index_4": [],
    }
    for library in libraries:
        data["library_id"].append(library.id)
        data["library_name"].append(library.name)
        data["library_type"].append(library.type.value.description)
        data["adapter"].append("")
        data["index_1"].append("")
        data["index_2"].append("")
        data["index_3"].append("")
        data["index_4"].append("")

    df = pd.DataFrame(data).sort_values(by=["library_type", "library_name"])

    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


@pools_htmx.route("<int:pool_id>/add_indices", methods=["POST"])
@login_required
def add_indices(pool_id: int):
    if (pool := db.db_handler.get_pool(pool_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    index_form = forms.IndexForm()
    valid, index_form, df = index_form.custom_validate()

    if not valid or df is None:
        return make_response(
            render_template(
                "forms/index.html", index_form=index_form
            )
        )

    for _, row in df.iterrows():
        library = db.db_handler.get_library(row["library_id"])
        library.index_1_sequence = row["index_1"] if not pd.isna(row["index_1"]) else None
        library.index_2_sequence = row["index_2"] if not pd.isna(row["index_2"]) else None
        library.index_3_sequence = row["index_3"] if not pd.isna(row["index_3"]) else None
        library.index_4_sequence = row["index_4"] if not pd.isna(row["index_4"]) else None
        library.index_1_adapter = row["adapter_1"] if not pd.isna(row["adapter_1"]) else None
        library.index_2_adapter = row["adapter_2"] if not pd.isna(row["adapter_2"]) else None
        library.index_3_adapter = row["adapter_3"] if not pd.isna(row["adapter_3"]) else None
        library.index_4_adapter = row["adapter_4"] if not pd.isna(row["adapter_4"]) else None
        db.db_handler.update_library(library)

    flash(f"Indices added succesfully to pool {pool.name}", "success")
    logger.debug(f"Indices added succesfully to pool {pool.name} ({pool.id})")
    return make_response(
        redirect=url_for("pools_page.pool_page", pool_id=pool_id),
    )
