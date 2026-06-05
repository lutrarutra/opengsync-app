from typing import Literal


from flask import Blueprint, render_template, request, flash, url_for
from flask_htmx import make_response

from opengsync_db import models, queries as Q
from opengsync_db.categories import PoolStatus, LibraryStatus, AccessLevel

from ... import db, forms, logic
from ...core import wrappers, exceptions
pools_htmx = Blueprint("pools_htmx", __name__, url_prefix="/htmx/pools/")


@wrappers.htmx_route(pools_htmx, db=db)
def get(current_user: models.User):
    return make_response(render_template(**logic.pool.get_table_context(current_user, request)))

@wrappers.htmx_route(pools_htmx, db=db)
def search(current_user: models.User):
    context = logic.pool.get_search_context(current_user=current_user, request=request)
    return make_response(render_template(**context))


@wrappers.htmx_route(pools_htmx, methods=["GET", "POST"], db=db)
def create(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    form = forms.models.PoolForm("create", formdata=request.form, current_user=current_user)
    if request.method == "GET":
        return form.make_response()
    return form.process_request()

@wrappers.htmx_route(pools_htmx, db=db, methods=["GET", "POST"])
def clone(current_user: models.User, pool_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool := db.session.first(Q.pool.select(id=pool_id))) is None:
        raise exceptions.NotFoundException()
    
    form = forms.models.PoolForm("clone", pool=pool, current_user=current_user, formdata=request.form)
    if request.method == "GET":
        return form.make_response()
    return form.process_request()
    

@wrappers.htmx_route(pools_htmx, db=db)
def get_form(current_user: models.User, form_type: Literal["create", "edit"], pool_id: int | None = None):
    if form_type not in ["create", "edit"]:
        raise exceptions.BadRequestException()
    
    if form_type == "create":
        if pool_id is not None:
            raise exceptions.BadRequestException()
        
        form = forms.models.PoolForm("create", current_user=current_user)
        return form.make_response()
    
    if form_type == "edit":
        if pool_id is None:
            raise exceptions.BadRequestException()
        
        if (pool := db.session.first(Q.pool.select(id=pool_id))) is None:
            raise exceptions.NotFoundException()
        
        if not current_user.is_insider() and pool.owner_id != current_user.id:
            raise exceptions.NoPermissionsException()
        
        form = forms.models.PoolForm("edit", current_user=current_user, pool=pool)
        return form.make_response()
    

@wrappers.htmx_route(pools_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, pool_id: int):
    if (pool := db.session.first(Q.pool.select(id=pool_id))) is None:
        raise exceptions.NotFoundException()
    
    access_level = db.session.get_access_level(Q.pool.permissions(pool.id, current_user.id))
    if access_level < AccessLevel.WRITE:
        raise exceptions.NoPermissionsException()
    
    form = forms.models.PoolForm("edit", current_user=current_user, pool=pool, formdata=request.form)
    if request.method == "GET":
        return form.make_response()
    
    return form.process_request()


@wrappers.htmx_route(pools_htmx, methods=["DELETE"], db=db)
def delete(current_user: models.User, pool_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool := db.session.first(Q.pool.select(id=pool_id))) is None:
        raise exceptions.NotFoundException()
    
    if len(pool.libraries) > 0:
        raise exceptions.NoPermissionsException()
    
    db.session.delete(pool)
    flash("Pool deleted", "success")
    return make_response(redirect=url_for("pools_page.pools"))


@wrappers.htmx_route(pools_htmx, methods=["DELETE"], db=db)
def remove_libraries(current_user: models.User, pool_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool := db.session.first(Q.pool.select(id=pool_id))) is None:
        raise exceptions.NotFoundException()
    
    if pool.status != PoolStatus.DRAFT and not current_user.is_admin():
        raise exceptions.NoPermissionsException()

    for library in pool.libraries:
        library.pool_id = None
        if library.status == LibraryStatus.POOLED:
            library.status = LibraryStatus.STORED

    db.session.save(pool)
    
    flash("Libraries removed from pool", "success")
    return make_response(redirect=url_for("pools_page.pool", pool_id=pool_id))


@wrappers.htmx_route(pools_htmx, methods=["DELETE"], db=db)
def remove_library(current_user: models.User, pool_id: int, library_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool := db.session.first(Q.pool.select(id=pool_id))) is None:
        raise exceptions.NotFoundException()
    
    if (library := db.session.first(Q.library.select(id=library_id))) is None:
        raise exceptions.NotFoundException()
    
    if library.pool_id != pool.id:
        raise exceptions.BadRequestException()
    
    pool.libraries.remove(library)
    if library.status == LibraryStatus.POOLED:
        library.status = LibraryStatus.STORED

    if library.experiment_id == pool.experiment_id:
        library.experiment_id = None

    db.session.save(library)
    db.session.save(pool)
    db.session.flush()

    db.session.refresh(pool)

    flash("Library Removed!", "success")

    context = logic.library.get_table_context(current_user, request, pool=pool)
    return make_response(render_template(**context))


@wrappers.htmx_route(pools_htmx, db=db, methods=["GET", "POST"])
def plate_pool(current_user: models.User, pool_id: int, form_type: Literal["create", "edit"]):
    if form_type not in ["create", "edit"]:
        raise exceptions.BadRequestException()
    if (pool := db.session.first(Q.pool.select(id=pool_id))) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider() and pool.owner_id != current_user.id:
        raise exceptions.NoPermissionsException()
    
    form = forms.models.PlateForm(form_type=form_type, pool=pool, formdata=request.form)
    
    if request.method == "GET":
        return form.make_response()
    
    return form.process_request(user=current_user)


@wrappers.htmx_route(pools_htmx, db=db)
def get_dilutions(current_user: models.User, pool_id: int):
    if (pool := db.session.first(Q.pool.select(id=pool_id))) is None:
        raise exceptions.NotFoundException()
    return make_response(render_template(**logic.dilution.get_table_context(current_user, request, pool=pool)))


@wrappers.htmx_route(pools_htmx, db=db)
def browse(current_user: models.User, workflow: str, page: int = 0):
    return make_response(render_template(**logic.pool.get_browse_context(current_user, request, workflow=workflow, page=page)))

@wrappers.htmx_route(pools_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get_recent(current_user: models.User, page: int = 0):
    PAGE_LIMIT = 10
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    # pools, _ = db.pools.find(
    #     status_in=[PoolStatus.STORED, PoolStatus.ACCEPTED], sort_by="id", descending=True,
    #     limit=PAGE_LIMIT, offset=page * PAGE_LIMIT
    # )

    pools = db.session.get_all(
        Q.pool.select(
            status_in=[PoolStatus.STORED, PoolStatus.ACCEPTED],
        ), limit=PAGE_LIMIT, offset=page * PAGE_LIMIT,
        order_by=models.Pool.id.desc()
    )
    
    return make_response(render_template(
        "components/dashboard/pools-list.html",
        pools=pools, sort_by="id",
        limit=PAGE_LIMIT, current_page=page
    ))