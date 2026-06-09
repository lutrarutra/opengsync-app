from flask import Blueprint, render_template, request, url_for
from flask_htmx import make_response

from opengsync_db import models, categories as C, queries as Q

from ... import db, forms, logic
from ...core import wrappers, exceptions

auth_htmx = Blueprint("auth_htmx", __name__, url_prefix="/htmx/auth/")
design_htmx = Blueprint("design_htmx", __name__, url_prefix="/htmx/design/")

@wrappers.htmx_route(design_htmx, db=db)
def flow_cells(current_user: models.User):
    return make_response(render_template(**logic.design.get_flow_cell_list_context(current_user, request)))

@wrappers.htmx_route(design_htmx, db=db)
def archived_flow_cells(current_user: models.User):
    return make_response(render_template(**logic.design.get_flow_cell_list_context(current_user, request, archived=True)))

@wrappers.htmx_route(design_htmx, db=db, methods=["POST"], arg_params=["pool_design_id"])
def create_flow_cell_design(current_user: models.User, pool_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool_design := db.session.first(Q.pool_design.select(id=pool_design_id))) is None:
        raise exceptions.NotFoundException("Pool Design not found")
    
    name = f"Flow Cell Design {db.session.query(models.FlowCellDesign).count() + 1}"

    flow_cell_design = Q.flow_cell_design.create(
        name=name[:models.FlowCellDesign.name.type.length],
    )
    flow_cell_design.pool_designs = [pool_design]
    db.session.save(flow_cell_design)

    return make_response(redirect=url_for("design_page.design"))

@wrappers.htmx_route(design_htmx, db=db, methods=["GET", "POST"])
def create_pool_design(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    form = forms.models.PoolDesignForm(pool_design=None, formdata=request.form)
    if request.method == "POST":
        return form.process_request()
    
    return form.make_response()
    

@wrappers.htmx_route(design_htmx, db=db, methods=["DELETE"])
def delete_pool_design(current_user: models.User, pool_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool_design := db.session.first(Q.pool_design.select(id=pool_design_id))) is None:
        raise exceptions.NotFoundException("Pool Design not found")
    
    db.session.delete(pool_design)
    db.session.flush()
    
    return make_response(redirect=url_for("design_page.design"))


@wrappers.htmx_route(design_htmx, db=db, methods=["DELETE"])
def remove_pool_design(current_user: models.User, pool_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool_design := db.session.first(Q.pool_design.select(id=pool_design_id))) is None:
        raise exceptions.NotFoundException("Pool Design not found")
    
    pool_design.flow_cell_design = None
    db.session.save(pool_design)
    return make_response(redirect=url_for("design_page.design"))


@wrappers.htmx_route(design_htmx, db=db, methods=["DELETE"])
def delete_flow_cell_design(current_user: models.User, flow_cell_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (flow_cell_design := db.session.first(Q.flow_cell_design.select(id=flow_cell_design_id))) is None:
        raise exceptions.NotFoundException("Flow Cell Design not found")
    
    for pool_design in flow_cell_design.pool_designs:
        pool_design.flow_cell_design = None
        db.session.save(pool_design)

    db.session.delete(flow_cell_design)
    return make_response(redirect=url_for("design_page.design"))


@wrappers.htmx_route(design_htmx, db=db, methods=["POST"], arg_params=["pool_design_id", "new_flow_cell_design_id"])
def move_pool_design(current_user: models.User, pool_design_id: int, new_flow_cell_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool_design := db.session.first(Q.pool_design.select(id=pool_design_id))) is None:
        raise exceptions.NotFoundException("Pool Design not found")
    
    if (new_flow_cell_design := db.session.first(Q.flow_cell_design.select(id=new_flow_cell_design_id))) is None:
        raise exceptions.NotFoundException("Flow Cell Design not found")
    
    pool_design.flow_cell_design = new_flow_cell_design
    db.session.save(pool_design)
    return make_response(redirect=url_for("design_page.design"))


@wrappers.htmx_route(design_htmx, db=db, methods=["GET", "POST"], arg_params=["todo_comment_id", "flow_cell_design_id", "pool_design_id"])
def comment_form(current_user: models.User, todo_comment_id: int | None = None, flow_cell_design_id: int | None = None, pool_design_id: int | None = None):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    todo_comment = None
    flow_cell_design = None
    pool_design = None

    if todo_comment_id is not None:
        if (todo_comment := db.session.first(Q.todo_comment.select(id=todo_comment_id))) is None:
            raise exceptions.NotFoundException("TODO Comment not found")
    
    if flow_cell_design_id is not None:
        if (flow_cell_design := db.session.first(Q.flow_cell_design.select(id=flow_cell_design_id))) is None:
            raise exceptions.NotFoundException("Flow Cell Design not found")
    
    if pool_design_id is not None:
        if (pool_design := db.session.first(Q.pool_design.select(id=pool_design_id))) is None:
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
        raise exceptions.NoPermissionsException()
    
    if (todo_comment := db.session.first(Q.todo_comment.select(id=todo_comment_id))) is None:
        raise exceptions.NotFoundException("TODO Comment not found")
    
    todo_comment.task_status_id = new_status_id
    db.session.save(todo_comment)
    
    return make_response(render_template(**logic.design.get_flow_cell_list_context(current_user, request)))


@wrappers.htmx_route(design_htmx, db=db, methods=["GET"])
def render_pool_designs(current_user: models.User, flow_cell_design_id: int | None = None):
    return make_response(render_template(**logic.design.get_pool_list_context(current_user, request, flow_cell_design_id=flow_cell_design_id)))


@wrappers.htmx_route(design_htmx, db=db, methods=["DELETE"], arg_params=["todo_comment_id"])
def delete_comment(current_user: models.User, todo_comment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (todo_comment := db.session.first(Q.todo_comment.select(id=todo_comment_id))) is None:
        raise exceptions.NotFoundException("TODO Comment not found")
    
    db.session.delete(todo_comment)
    db.session.save(todo_comment)
    
    return make_response(redirect=url_for("design_page.design"))


@wrappers.htmx_route(design_htmx, db=db, methods=["POST"], arg_params=["flow_cell_design_id", "flow_cell_type_id"])
def set_flow_cell_type(current_user: models.User, flow_cell_design_id: int, flow_cell_type_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (flow_cell_design := db.session.first(Q.flow_cell_design.select(id=flow_cell_design_id))) is None:
        raise exceptions.NotFoundException("Flow Cell Design not found")
    
    if flow_cell_type_id == -1:
        flow_cell_design.flow_cell_type = None
    else:
        flow_cell_design.flow_cell_type = C.FlowCellType.get(flow_cell_type_id)
    
    db.session.save(flow_cell_design)
    
    return make_response(redirect=url_for("design_page.design"))


@wrappers.htmx_route(design_htmx, db=db, methods=["POST"], arg_params=["flow_cell_design_id"])
def archive_flow_cell_design(current_user: models.User, flow_cell_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (flow_cell_design := db.session.first(Q.flow_cell_design.select(id=flow_cell_design_id))) is None:
        raise exceptions.NotFoundException("Flow Cell Design not found")
    
    flow_cell_design.task_status = C.TaskStatus.ARCHIVED
    db.session.save(flow_cell_design)

    return make_response(redirect=url_for("design_page.design"))

@wrappers.htmx_route(design_htmx, db=db, methods=["POST"], arg_params=["flow_cell_design_id"])
def unarchive_flow_cell_design(current_user: models.User, flow_cell_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (flow_cell_design := db.session.first(Q.flow_cell_design.select(id=flow_cell_design_id))) is None:
        raise exceptions.NotFoundException("Flow Cell Design not found")
    
    flow_cell_design.task_status = C.TaskStatus.DRAFT
    db.session.save(flow_cell_design)

    return make_response(redirect=url_for("design_page.design"))


@wrappers.htmx_route(design_htmx, db=db, methods=["GET", "POST"])
def edit_flow_cell_design(current_user: models.User, flow_cell_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (flow_cell_design := db.session.first(Q.flow_cell_design.select(id=flow_cell_design_id))) is None:
        raise exceptions.NotFoundException("Flow Cell Design not found")
    
    if request.method == "GET":
        form = forms.models.FlowCellDesignForm(flow_cell_design)
        return form.make_response()
    
    form = forms.models.FlowCellDesignForm(flow_cell_design, formdata=request.form)
    return form.process_request()


@wrappers.htmx_route(design_htmx, db=db, methods=["GET", "POST"])
def edit_pool_design(current_user: models.User, pool_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (pool_design := db.session.first(Q.pool_design.select(id=pool_design_id))) is None:
        raise exceptions.NotFoundException("Pool Design not found")
    
    if request.method == "GET":
        form = forms.models.PoolDesignForm(pool_design)
        return form.make_response()
    
    form = forms.models.PoolDesignForm(pool_design, formdata=request.form)
    return form.process_request()