from flask import Blueprint, url_for, render_template, flash, request
from flask_htmx import make_response

from opengsync_db import PAGE_LIMIT, exceptions as db_exc, models
from opengsync_db.categories import UserRole

from .... import db, forms
from ....core import wrappers, exceptions

sequencers_htmx = Blueprint("sequencers_htmx", __name__, url_prefix="/api/hmtx/sequencers/")


@wrappers.htmx_route(sequencers_htmx, db=db, cache_timeout_seconds=60, cache_type="user")
def get(current_user: models.User, page: int = 0):
    if current_user.role != UserRole.ADMIN:
        raise exceptions.NoPermissionsException()
    
    sequencers, n_pages = db.sequencers.find(offset=PAGE_LIMIT * page, count_pages=True)
    
    return make_response(
        render_template(
            "components/tables/sequencer.html",
            sequencers=sequencers,
            n_pages=n_pages,
            active_page=page
        )
    )


@wrappers.htmx_route(sequencers_htmx, db=db, methods=["POST"])
def create(current_user: models.User):
    if current_user.role != UserRole.ADMIN:
        raise exceptions.NoPermissionsException()

    return forms.models.SequencerForm(request.form).process_request()


@wrappers.htmx_route(sequencers_htmx, db=db, methods=["POST"])
def update(current_user: models.User, sequencer_id: int):
    if current_user.role != UserRole.ADMIN:
        raise exceptions.NoPermissionsException()
    
    if (sequencer := db.sequencers.get(sequencer_id)) is None:
        raise exceptions.NotFoundException()

    return forms.models.SequencerForm(request.form).process_request(
        sequencer=sequencer
    )


@wrappers.htmx_route(sequencers_htmx, db=db)
def delete(current_user: models.User, sequencer_id: int):
    if current_user.role != UserRole.ADMIN:
        raise exceptions.NoPermissionsException()

    if db.sequencers.get(sequencer_id) is None:
        raise exceptions.NotFoundException()
    
    try:
        db.sequencers.delete(sequencer_id)
    except db_exc.ElementIsReferenced:
        flash("Sequencer is referenced by experiment(s) and cannot be deleted.", "error")
        return make_response(
            redirect=url_for("devices_page.sequencer", sequencer_id=sequencer_id)
        )

    flash("Sequencer deleted.", "success")
    return make_response(
        redirect=url_for("devices_page.devices")
    )


@wrappers.htmx_route(sequencers_htmx, db=db, methods=["POST"])
def query():
    field_name = next(iter(request.form.keys()))
    query = request.form.get(field_name)

    if query is None:
        raise exceptions.BadRequestException()
    
    results = db.sequencers.query(query)
    
    return make_response(
        render_template(
            "components/search/sequencer.html",
            results=results,
            field_name=field_name
        )
    )
