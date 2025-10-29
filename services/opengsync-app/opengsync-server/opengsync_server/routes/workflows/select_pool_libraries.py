from flask import Blueprint, Response, url_for, request, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import LibraryStatus

from ... import db, logger
from ...core import wrappers, exceptions
from ...forms import SelectSamplesForm

select_pool_libraries_workflow = Blueprint("select_pool_libraries_workflow", __name__, url_prefix="/workflows/select_pool_libraries/")


@wrappers.htmx_route(select_pool_libraries_workflow, db=db)
def begin(current_user: models.User, pool_id: int) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
        
    form = SelectSamplesForm(
        "select_pool_libraries",
        select_libraries=True,
        context={"pool": pool},
        library_status_filter=[
            LibraryStatus.DRAFT,
            LibraryStatus.SUBMITTED,
            LibraryStatus.ACCEPTED,
            LibraryStatus.PREPARING,
            LibraryStatus.STORED,
        ]
    )
    return form.make_response()


@wrappers.htmx_route(select_pool_libraries_workflow, db=db, methods=["POST"])
def select(current_user: models.User, pool_id: int) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()

    form = SelectSamplesForm(
        "select_pool_libraries",
        select_libraries=True,
        context={"pool": pool},
        library_status_filter=[
            LibraryStatus.DRAFT,
            LibraryStatus.SUBMITTED,
            LibraryStatus.PREPARING,
            LibraryStatus.STORED,
        ],
        formdata=request.form,
    )
    if not form.validate():
        return form.make_response()
    
    library_ids = form.library_table["id"].unique().tolist()
    for library_id in library_ids:
        db.libraries.add_to_pool(library_id=int(library_id), pool_id=pool.id, flush=False)

    db.flush()
    flash("Libraries added to pool!", "success")
    return make_response(redirect=url_for("pools_page.pool", pool_id=pool.id))
        