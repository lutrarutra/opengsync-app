import json
from typing import TYPE_CHECKING, Literal

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, PoolStatus

from .... import db, forms, logger  # noqa

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

pools_htmx = Blueprint("pools_htmx", __name__, url_prefix="/api/hmtx/pools/")


@pools_htmx.route("get/<int:page>", methods=["GET"])
@pools_htmx.route("get", methods=["GET"], defaults={"page": 0})
@login_required
def get(page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [PoolStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    pools, n_pages = db.get_pools(
        sort_by=sort_by, descending=descending,
        offset=offset, status_in=status_in
    )

    return make_response(
        render_template(
            "components/tables/pool.html", pools=pools, n_pages=n_pages,
            sort_by=sort_by, sort_order=sort_order,
            active_page=page, PoolStatus=PoolStatus, status_in=status_in
        )
    )


@pools_htmx.route("create", methods=["POST"])
@login_required
def create():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.models.PoolForm("create", formdata=request.form)
    return form.process_request(user=current_user)


@pools_htmx.route("get_form/<string:form_type>", methods=["GET"])
@login_required
def get_form(form_type: Literal["create", "edit"]):
    if form_type not in ["create", "edit"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if form_type == "create":
        if (pool_id := request.args.get("pool_id")) is not None:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        form = forms.models.PoolForm("create")
        form.contact.selected.data = current_user.id
        form.contact.search_bar.data = current_user.name
        return form.make_response()
    
    if form_type == "edit":
        if (pool_id := request.args.get("pool_id")) is None:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        try:
            pool_id = int(pool_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        with DBSession(db) as session:
            if (pool := session.get_pool(pool_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            
            if not current_user.is_insider() and pool.owner_id != current_user.id:
                return abort(HTTPResponse.FORBIDDEN.id)
            
            form = forms.models.PoolForm("edit")
            form.prepare(pool)
            return form.make_response()
    

@pools_htmx.route("<int:pool_id>/edit", methods=["POST"])
@login_required
def edit(pool_id: int):
    with DBSession(db) as session:
        if (pool := session.get_pool(pool_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if not current_user.is_insider() and pool.owner_id != current_user.id:
            return abort(HTTPResponse.FORBIDDEN.id)
        return forms.models.PoolForm("edit", formdata=request.form).process_request(user=current_user, pool=pool)


@pools_htmx.route("table_query", methods=["GET"])
@login_required
def table_query():
    if (word := request.args.get("name", None)) is not None:
        field_name = "name"
    elif (word := request.args.get("id", None)) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if word is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if field_name == "name":
        pools = db.query_pools(word)
    elif field_name == "id":
        try:
            pools = [db.get_pool(int(word))]
        except ValueError:
            pools = []

    return make_response(
        render_template(
            "components/tables/pool.html",
            pools=pools, field_name=field_name,
            current_query=word, Pool=models.Pool,
        )
    )


@pools_htmx.route("<int:pool_id>/get_libraries/<int:page>", methods=["GET"])
@pools_htmx.route("<int:pool_id>/get_libraries", methods=["GET"], defaults={"page": 0})
@login_required
def get_libraries(pool_id: int, page: int):
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and pool.owner_id != current_user.id:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    libraries, n_pages = db.get_libraries(offset=offset, pool_id=pool_id, sort_by=sort_by, descending=descending)
    
    return make_response(
        render_template(
            "components/tables/pool-library.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, pool=pool
        )
    )


@pools_htmx.route("<int:pool_id>/get_plate", methods=["GET"])
@login_required
def get_plate(pool_id: int):
    with DBSession(db) as session:
        if (pool := session.get_pool(pool_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        plates, _ = session.get_plates(pool_id=pool_id)
        plate = plates[0] if len(plates) > 0 else None
        library_plate_links = plate.library_links if plate is not None else []
    
        if not current_user.is_insider() and pool.owner_id != current_user.id:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    return make_response(
        render_template(
            "components/plate.html", pool=pool, plate=plate, library_plate_links=library_plate_links
        )
    )


@pools_htmx.route("<int:pool_id>/plate_pool/<string:form_type>", methods=["GET", "POST"])
@login_required
def plate_pool(pool_id: int, form_type: Literal["create", "edit"]):
    if form_type not in ["create", "edit"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and pool.owner_id != current_user.id:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.models.PlateForm(form_type=form_type, pool=pool, formdata=request.form)
    
    if request.method == "GET":
        form.prepare()
        return form.make_response()
    
    return form.process_request(user=current_user)


@pools_htmx.route("<int:pool_id>/query_libraries", methods=["GET"])
@login_required
def query_libraries(pool_id: int):
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if pool.owner != current_user.id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    libraries: list[models.Library] = []
    if field_name == "name":
        libraries = db.query_libraries(word, pool_id=pool_id)
    elif field_name == "id":
        try:
            _id = int(word)
            if (library := db.get_library(_id)) is not None:
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


@pools_htmx.route("<int:pool_id>/get_dilutions/<int:page>", methods=["GET"])
@pools_htmx.route("<int:pool_id>/get_dilutions", methods=["GET"], defaults={"page": 0})
@login_required
def get_dilutions(pool_id: int, page: int):
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and pool.owner_id != current_user.id:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    dilutions, n_pages = db.get_pool_dilutions(offset=offset, pool_id=pool_id, sort_by=sort_by, descending=descending, limit=None)
    
    return make_response(
        render_template(
            "components/tables/pool-dilution.html",
            dilutions=dilutions, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, pool=pool
        )
    )