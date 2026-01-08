from flask import Blueprint, render_template, request, url_for
from flask_htmx import make_response

from opengsync_db import models, categories as cats

from ... import db, forms, logger
from ...tools import textgen
from ...core import wrappers, exceptions, runtime

auth_htmx = Blueprint("auth_htmx", __name__, url_prefix="/htmx/auth/")
design_htmx = Blueprint("design_htmx", __name__, url_prefix="/htmx/design/")

@wrappers.htmx_route(design_htmx, db=db)
def flow_cells(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    designs = db.session.query(models.FlowCellDesign).order_by(models.FlowCellDesign.id.desc()).all()

    orphan_pool_designs = db.session.query(models.PoolDesign).filter(
        models.PoolDesign.flow_cell_design_id.is_(None)
    ).all()

    return make_response(render_template(
        "components/design/flow_cell_design-list.html", designs=designs,
        orphan_pool_designs=orphan_pool_designs,
    ))

@wrappers.htmx_route(design_htmx, db=db, methods=["POST"], arg_params=["pool_design_id"])
def create_flow_cell_design(current_user: models.User, pool_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if (pool_design := db.session.get(models.PoolDesign, pool_design_id)) is None:
        raise exceptions.NotFoundException("Pool Design not found")
    
    if textgen is None:
        name = f"Flow Cell Design {db.session.query(models.FlowCellDesign).count() + 1}"
    else:
        name = textgen.generate(
            "Come up with a short unique animal-themed name. It can be two or more words, like Small Whale or Lazy Otter. Reply only with the name. No special characters.",
        ) or f"Flow Cell Design {db.session.query(models.FlowCellDesign).count() + 1}"

    flow_cell_design = models.FlowCellDesign(
        name=name,
        pool_designs=[pool_design],
    )

    db.session.add(flow_cell_design)
    db.flush()

    return make_response(redirect=url_for("design_page.design"))

@wrappers.htmx_route(design_htmx, db=db, methods=["GET", "POST"])
def create_pool_design(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    form = forms.models.PoolDesignForm(pool_design=None, formdata=request.form)
    if request.method == "POST":
        return form.process_request()
    
    return form.make_response()
    

@wrappers.htmx_route(design_htmx, db=db, methods=["DELETE"])
def delete_pool_design(current_user: models.User, pool_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if (pool_design := db.session.get(models.PoolDesign, pool_design_id)) is None:
        raise exceptions.NotFoundException("Pool Design not found")
    
    db.session.delete(pool_design)
    db.flush()
    
    return make_response(redirect=url_for("design_page.design"))


@wrappers.htmx_route(design_htmx, db=db, methods=["DELETE"])
def remove_pool_design(current_user: models.User, pool_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if (pool_design := db.session.get(models.PoolDesign, pool_design_id)) is None:
        raise exceptions.NotFoundException("Pool Design not found")
    
    pool_design.flow_cell_design = None
    db.flush()
    
    return make_response(redirect=url_for("design_page.design"))


@wrappers.htmx_route(design_htmx, db=db, methods=["DELETE"])
def delete_flow_cell_design(current_user: models.User, flow_cell_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if (flow_cell_design := db.session.get(models.FlowCellDesign, flow_cell_design_id)) is None:
        raise exceptions.NotFoundException("Flow Cell Design not found")
    
    for pool_design in flow_cell_design.pool_designs:
        pool_design.flow_cell_design = None
    db.session.delete(flow_cell_design)
    db.flush()
    
    return make_response(redirect=url_for("design_page.design"))


@wrappers.htmx_route(design_htmx, db=db, methods=["POST"], arg_params=["pool_design_id", "new_flow_cell_design_id"])
def move_pool_design(current_user: models.User, pool_design_id: int, new_flow_cell_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if (pool_design := db.session.get(models.PoolDesign, pool_design_id)) is None:
        raise exceptions.NotFoundException("Pool Design not found")
    
    if (new_flow_cell_design := db.session.get(models.FlowCellDesign, new_flow_cell_design_id)) is None:
        raise exceptions.NotFoundException("Flow Cell Design not found")
    
    pool_design.flow_cell_design = new_flow_cell_design
    db.flush()
    
    designs = db.session.query(models.FlowCellDesign).order_by(models.FlowCellDesign.id.desc()).all()

    orphan_pool_designs = db.session.query(models.PoolDesign).filter(
        models.PoolDesign.flow_cell_design_id.is_(None)
    ).all()

    return make_response(render_template(
        "components/design/flow_cell_design-list.html", designs=designs,
        orphan_pool_designs=orphan_pool_designs,
    ))


@wrappers.htmx_route(design_htmx, db=db, methods=["GET", "POST"], arg_params=["todo_comment_id", "flow_cell_design_id", "pool_design_id"])
def comment_form(current_user: models.User, todo_comment_id: int | None = None, flow_cell_design_id: int | None = None, pool_design_id: int | None = None):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    todo_comment = None
    flow_cell_design = None
    pool_design = None

    if todo_comment_id is not None:
        if (todo_comment := db.session.get(models.TODOComment, todo_comment_id)) is None:
            raise exceptions.NotFoundException("TODO Comment not found")
    
    if flow_cell_design_id is not None:
        if (flow_cell_design := db.session.get(models.FlowCellDesign, flow_cell_design_id)) is None:
            raise exceptions.NotFoundException("Flow Cell Design not found")
    
    if pool_design_id is not None:
        if (pool_design := db.session.get(models.PoolDesign, pool_design_id)) is None:
            raise exceptions.NotFoundException("Pool Design not found")
    
    form = forms.models.TODOCommentForm(
        todo_comment=todo_comment,
        flow_cell_design=flow_cell_design,
        pool_design=pool_design,
        formdata=request.form
    )
    
    if request.method == "POST":
        return form.process_request(current_user=current_user)
    
    return form.make_response()


@wrappers.htmx_route(design_htmx, db=db, methods=["POST"], arg_params=["todo_comment_id", "new_status_id"])
def edit_comment_status(current_user: models.User, todo_comment_id: int, new_status_id: int | None):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if (todo_comment := db.session.get(models.TODOComment, todo_comment_id)) is None:
        raise exceptions.NotFoundException("TODO Comment not found")
    
    todo_comment.task_status_id = new_status_id
    db.flush()
    
    designs = db.session.query(models.FlowCellDesign).order_by(models.FlowCellDesign.id.desc()).all()

    orphan_pool_designs = db.session.query(models.PoolDesign).filter(
        models.PoolDesign.flow_cell_design_id.is_(None)
    ).all()

    return make_response(render_template(
        "components/design/flow_cell_design-list.html", designs=designs,
        orphan_pool_designs=orphan_pool_designs,
    ))


@wrappers.htmx_route(design_htmx, db=db, methods=["GET"])
def render_pool_designs(current_user: models.User, flow_cell_design_id: int | None = None):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if flow_cell_design_id is not None:
        if (flow_cell_design := db.session.get(models.FlowCellDesign, flow_cell_design_id)) is None:
            raise exceptions.NotFoundException("Flow Cell Design not found")
    else:
        flow_cell_design = None
    
    query = db.session.query(models.PoolDesign)
    if flow_cell_design_id is not None:
        query = query.filter(models.PoolDesign.flow_cell_design_id == flow_cell_design_id)
    else:
        query = query.filter(models.PoolDesign.flow_cell_design_id.is_(None))
    pool_designs = query.order_by(models.PoolDesign.id.desc()).all()

    return make_response(render_template("components/design/pool_design-list.html", pool_designs=pool_designs, flow_cell_design=flow_cell_design))


@wrappers.htmx_route(design_htmx, db=db, methods=["DELETE"], arg_params=["todo_comment_id"])
def delete_comment(current_user: models.User, todo_comment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if (todo_comment := db.session.get(models.TODOComment, todo_comment_id)) is None:
        raise exceptions.NotFoundException("TODO Comment not found")
    
    db.session.delete(todo_comment)
    db.flush()
    
    designs = db.session.query(models.FlowCellDesign).order_by(models.FlowCellDesign.id.desc()).all()

    orphan_pool_designs = db.session.query(models.PoolDesign).filter(
        models.PoolDesign.flow_cell_design_id.is_(None)
    ).all()

    return make_response(render_template(
        "components/design/flow_cell_design-list.html", designs=designs,
        orphan_pool_designs=orphan_pool_designs,
    ))

@wrappers.htmx_route(design_htmx, db=db, methods=["POST"], arg_params=["flow_cell_design_id", "flow_cell_type_id"])
def set_flow_cell_type(current_user: models.User, flow_cell_design_id: int, flow_cell_type_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if (flow_cell_design := db.session.get(models.FlowCellDesign, flow_cell_design_id)) is None:
        raise exceptions.NotFoundException("Flow Cell Design not found")
    
    if flow_cell_type_id == -1:
        flow_cell_design.flow_cell_type = None
    else:
        flow_cell_design.flow_cell_type = cats.FlowCellType.get(flow_cell_type_id)
    
    db.session.add(flow_cell_design)
    db.flush()
    
    designs = db.session.query(models.FlowCellDesign).order_by(models.FlowCellDesign.id.desc()).all()

    orphan_pool_designs = db.session.query(models.PoolDesign).filter(
        models.PoolDesign.flow_cell_design_id.is_(None)
    ).all()

    return make_response(render_template(
        "components/design/flow_cell_design-list.html", designs=designs,
        orphan_pool_designs=orphan_pool_designs,
    ))
