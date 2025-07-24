from typing import TYPE_CHECKING

from flask import Blueprint, abort, Response, url_for, request, flash
from flask_login import login_required
from flask_htmx import make_response

from opengsync_db import models, db_session, exceptions
from opengsync_db.categories import HTTPResponse, LibraryStatus

from .... import db, logger  # noqa
from ....forms import SelectSamplesForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user  # noqa

select_pool_libraries_workflow = Blueprint("select_pool_libraries_workflow", __name__, url_prefix="/api/workflows/select_pool_libraries/")


@select_pool_libraries_workflow.route("begin/<int:pool_id>", methods=["GET"])
@db_session(db)
@login_required
def begin(pool_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
        
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


@select_pool_libraries_workflow.route("select/<int:pool_id>", methods=["POST"])
@db_session(db)
@login_required
def select(pool_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

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
        if (library := db.get_library(int(library_id))) is None:
            logger.error(f"Library with ID {library_id} not found in pool {pool_id}.")
            raise exceptions.ElementDoesNotExist(f"Library with ID {library_id} does not exist.")
        
        if library.pool_id is not None:
            logger.error(f"Library {library_id} is already in a pool.")
            raise exceptions.LinkAlreadyExists(f"Library {library_id} is already in a pool.")
    
        db.add_library_to_pool(library_id=library.id, pool_id=pool.id, flush=False)

    db.flush()
    flash("Libraries added to pool!", "success")
    return make_response(redirect=url_for("pools_page.pool_page", pool_id=pool.id))
        