from typing import TYPE_CHECKING

from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required

from ... import db, forms, logger, PAGE_LIMIT
from ...core import DBSession
from ...models import User
from ...categories import UserRole, HttpResponse

if TYPE_CHECKING:
    current_user: User = None
else:
    from flask_login import current_user

pools_page_bp = Blueprint("pools_page", __name__)


@pools_page_bp.route("/pools")
@login_required
def pools_page():
    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            pools, n_pages = session.get_pools(limit=PAGE_LIMIT, user_id=current_user.id, sort_by="id", descending=True)
        else:
            pools, n_pages = session.get_pools(limit=PAGE_LIMIT, user_id=None, sort_by="id", descending=True)

    pool_form = forms.PoolForm()

    return render_template(
        "pools_page.html",
        pools=pools,
        index_kit_results=db.common_kits,
        pool_form=pool_form,
        pools_n_pages=n_pages, pools_active_page=0,
        current_sort="id", current_sort_order="desc"
    )


@pools_page_bp.route("/pools/<int:pool_id>")
@login_required
def pool_page(pool_id: int):
    with DBSession(db.db_handler) as session:
        if (pool := session.get_pool(pool_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if not current_user.is_insider():
            if pool.owner_id != current_user.id:
                return abort(HttpResponse.FORBIDDEN.value.id)
    
    pool_form = forms.PoolForm()
    pool_form.name.data = pool.name

    path_list = [
        ("Pools", url_for("pools_page.pools_page")),
        (f"Pool {pool.id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")

    return render_template(
        "pool_page.html",
        pool=pool,
        path_list=path_list,
        pool_form=pool_form,
        table_form=forms.TableForm(),
    )
