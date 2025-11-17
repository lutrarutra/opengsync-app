import json
from typing import Literal


from flask import Blueprint, render_template, request, flash, url_for
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import PoolStatus, LibraryStatus, PoolType

from ... import db, forms
from ...core import wrappers, exceptions
pools_htmx = Blueprint("pools_htmx", __name__, url_prefix="/htmx/pools/")


@wrappers.htmx_route(pools_htmx, db=db)
def get(current_user: models.User, page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [PoolStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [PoolType.get(int(type)) for type in type_in]
        except ValueError:
            raise exceptions.BadRequestException()

        if len(type_in) == 0:
            type_in = None

    pools, n_pages = db.pools.find(
        sort_by=sort_by, descending=descending, page=page, status_in=status_in, type_in=type_in
    )

    return make_response(
        render_template(
            "components/tables/pool.html", pools=pools, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order,
            active_page=page, status_in=status_in, type_in=type_in
        )
    )


@wrappers.htmx_route(pools_htmx, methods=["POST"], db=db)
def create(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    form = forms.models.PoolForm("create", formdata=request.form)
    return form.process_request(user=current_user)


@wrappers.htmx_route(pools_htmx, methods=["DELETE"], db=db)
def delete(current_user: models.User, pool_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if len(pool.libraries) > 0:
        raise exceptions.NoPermissionsException()
    
    db.pools.delete(pool.id)
    flash("Pool deleted", "success")
    return make_response(redirect=url_for("pools_page.pools"))


@wrappers.htmx_route(pools_htmx, methods=["DELETE"], db=db)
def remove_libraries(current_user: models.User, pool_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if pool.status != PoolStatus.DRAFT:
        raise exceptions.NoPermissionsException()

    for library in pool.libraries:
        library.pool_id = None
        if library.status == LibraryStatus.POOLED:
            library.status = LibraryStatus.STORED

    db.pools.update(pool)
    
    flash("Libraries removed from pool", "success")
    return make_response(redirect=url_for("pools_page.pool", pool_id=pool_id))


@wrappers.htmx_route(pools_htmx, db=db)
def get_form(current_user: models.User, form_type: Literal["create", "edit"], pool_id: int | None = None):
    if form_type not in ["create", "edit"]:
        raise exceptions.BadRequestException()
    
    if form_type == "create":
        if pool_id is not None:
            raise exceptions.BadRequestException()
        
        form = forms.models.PoolForm("create")
        form.contact.selected.data = current_user.id
        form.contact.search_bar.data = current_user.name
        return form.make_response()
    
    if form_type == "edit":
        if pool_id is None:
            raise exceptions.BadRequestException()
        
        if (pool := db.pools.get(pool_id)) is None:
            raise exceptions.NotFoundException()
        
        if not current_user.is_insider() and pool.owner_id != current_user.id:
            raise exceptions.NoPermissionsException()
        
        form = forms.models.PoolForm("edit", pool=pool)
        return form.make_response()
    

@wrappers.htmx_route(pools_htmx, methods=["POST"], db=db)
def edit(current_user: models.User, pool_id: int):
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider() and pool.owner_id != current_user.id:
        raise exceptions.NoPermissionsException()
    return forms.models.PoolForm("edit", pool=pool, formdata=request.form).process_request(user=current_user)


@wrappers.htmx_route(pools_htmx, methods=["GET", "POST"], db=db)
def clone(current_user: models.User, pool_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        form = forms.models.PoolForm("clone", pool=pool)
        return form.make_response()
    else:
        form = forms.models.PoolForm("clone", formdata=request.form, pool=pool)
        return form.process_request(user=current_user)


@wrappers.htmx_route(pools_htmx, methods=["DELETE"], db=db)
def remove_library(current_user: models.User, pool_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if (library_id := request.args.get("library_id")) is None:
        raise exceptions.BadRequestException()
    
    try:
        library_id = int(library_id)
    except ValueError:
        raise exceptions.BadRequestException()
    
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    if library.pool_id != pool.id:
        raise exceptions.BadRequestException()
    
    library.pool_id = None
    if library.status == LibraryStatus.POOLED:
        library.status = LibraryStatus.STORED

    if library.experiment_id == pool.experiment_id:
        library.experiment_id = None
    db.libraries.update(library)

    flash("Library removed from pool", "success")
    return make_response(redirect=url_for("pools_page.pool", pool_id=pool_id))


@wrappers.htmx_route(pools_htmx, db=db)
def table_query():
    if (word := request.args.get("name", None)) is not None:
        field_name = "name"
    elif (word := request.args.get("id", None)) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()
    
    if word is None:
        raise exceptions.BadRequestException()
    
    if field_name == "name":
        pools = db.pools.query(word)
    elif field_name == "id":
        try:
            pools = [db.pools.get(int(word))]
        except ValueError:
            pools = []
    else:
        raise exceptions.BadRequestException()

    return make_response(
        render_template(
            "components/tables/pool.html",
            pools=pools, field_name=field_name,
            current_query=word, Pool=models.Pool,
        )
    )


@wrappers.htmx_route(pools_htmx, methods=["POST"], db=db)
def query():
    field_name = next(iter(request.form.keys()))
    query = request.form.get(field_name)

    if query is None:
        raise exceptions.BadRequestException()
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [PoolStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
        except ValueError:
            raise exceptions.BadRequestException()

    results = db.pools.query(query, status_in=status_in, seq_request_id=seq_request_id)
    
    return make_response(
        render_template(
            "components/search/pool.html",
            results=results, field_name=field_name
        )
    )


@wrappers.htmx_route(pools_htmx, db=db)
def get_libraries(current_user: models.User, pool_id: int, page: int = 0):
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider() and pool.owner_id != current_user.id:
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    libraries, n_pages = db.libraries.find(page=page, pool_id=pool_id, sort_by=sort_by, descending=descending)
    
    return make_response(
        render_template(
            "components/tables/pool-library.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, pool=pool
        )
    )


@wrappers.htmx_route(pools_htmx, db=db)
def query_libraries(current_user: models.User, pool_id: int):
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()
    
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if pool.owner != current_user.id and not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    libraries: list[models.Library] = []
    if field_name == "name":
        libraries = db.libraries.query(name=word, pool_id=pool_id)
    elif field_name == "id":
        try:
            _id = int(word)
            if (library := db.libraries.get(_id)) is not None:
                if library.pool_id == pool_id:
                    libraries.append(library)
        except ValueError:
            pass

    return make_response(
        render_template(
            "components/tables/pool-library.html",
            current_query=word, active_query_field=field_name,
            pool=pool, libraries=libraries,
        )
    )


@wrappers.htmx_route(pools_htmx, db=db, methods=["GET", "POST"])
def plate_pool(current_user: models.User, pool_id: int, form_type: Literal["create", "edit"]):
    if form_type not in ["create", "edit"]:
        raise exceptions.BadRequestException()
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider() and pool.owner_id != current_user.id:
        raise exceptions.NoPermissionsException()
    
    form = forms.models.PlateForm(form_type=form_type, pool=pool, formdata=request.form)
    
    if request.method == "GET":
        return form.make_response()
    
    return form.process_request(user=current_user)


@wrappers.htmx_route(pools_htmx, db=db)
def get_dilutions(current_user: models.User, pool_id: int, page: int = 0):
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider() and pool.owner_id != current_user.id:
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    dilutions, n_pages = db.pools.get_dilutions(offset=offset, pool_id=pool_id, sort_by=sort_by, descending=descending, limit=None)
    
    return make_response(
        render_template(
            "components/tables/pool-dilution.html",
            dilutions=dilutions, active_page=page,
            sort_by=sort_by, sort_order=sort_order, pool=pool,
            n_pages=n_pages
        )
    )


@wrappers.htmx_route(pools_htmx, db=db)
def browse(current_user: models.User, workflow: str, page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    context = {}
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            context["experiment_id"] = experiment_id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            context["seq_request_id"] = seq_request_id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [PoolStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    associated_to_experiment = None
    if workflow == "select_experiment_pools":
        associated_to_experiment = False
        experiment_id = None

    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    
    pools, n_pages = db.pools.find(
        sort_by=sort_by, descending=descending, page=page, status_in=status_in, experiment_id=experiment_id,
        seq_request_id=seq_request_id, associated_to_experiment=associated_to_experiment
    )

    context["workflow"] = workflow
    return make_response(
        render_template(
            "components/tables/select-pools.html",
            pools=pools, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, context=context,
            status_in=status_in, workflow=workflow
        )
    )


@wrappers.htmx_route(pools_htmx, db=db)
def browse_query(current_user: models.User, workflow: str):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()
    
    context = {}
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            context["experiment_id"] = experiment_id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            context["seq_request_id"] = seq_request_id
        except ValueError:
            raise exceptions.BadRequestException()
    
    pools: list[models.Pool] = []
    if field_name == "name":
        pools = db.pools.query(word, experiment_id=experiment_id, seq_request_id=seq_request_id)
    elif field_name == "id":
        try:
            _id = int(word)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (pool := db.pools.get(pool_id=_id)) is not None:
            if pool.experiment_id == pool.id:
                pools.append(pool)
    else:
        raise exceptions.BadRequestException()
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [PoolStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
    
    context["workflow"] = workflow
    return make_response(
        render_template(
            "components/tables/select-pools.html",
            context=context, pools=pools, status_in=status_in,
            workflow=workflow
        )
    )


@wrappers.htmx_route(pools_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get_recent_pools(current_user: models.User, page: int = 0):
    PAGE_LIMIT = 10
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    pools, _ = db.pools.find(
        status_in=[PoolStatus.STORED, PoolStatus.ACCEPTED], sort_by="id", descending=True,
        limit=PAGE_LIMIT, offset=page * PAGE_LIMIT
    )
    
    return make_response(render_template(
        "components/dashboard/pools-list.html",
        pools=pools, sort_by="id",
        limit=PAGE_LIMIT, current_page=page
    ))