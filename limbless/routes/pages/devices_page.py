from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import login_required, current_user

from ...core import DBSession
from ... import forms, db, logger
from ...categories import UserRole, HttpResponse

devices_page_bp = Blueprint("devices_page", __name__)


@devices_page_bp.route("/devices")
@login_required
def devices_page():
    if current_user.role_type != UserRole.ADMIN:
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    sequencer_form = forms.SequencerForm()
    with DBSession(db.db_handler) as session:
        sequencers = session.get_sequencers()
        n_pages = int(session.get_num_sequencers() / 20)

    return render_template(
        "devices_page.html", sequencer_form=sequencer_form,
        sequencers=sequencers,
        n_pages=n_pages, active_page=0
    )


@devices_page_bp.route("/sequencers/<int:sequencer_id>", methods=["GET"])
@login_required
def sequencer_page(sequencer_id: int):
    if current_user.role_type != UserRole.ADMIN:
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (sequencer := db.db_handler.get_sequencer(sequencer_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    sequencer_form = forms.SequencerForm()
    sequencer_form.name.data = sequencer.name
    sequencer_form.ip_address.data = sequencer.ip

    path_list = [
        ("Devices", url_for("devices_page.devices_page")),
        (f"Device {sequencer.id}", ""),
    ]
    return render_template(
        "device_page.html", sequencer_form=sequencer_form,
        sequencer=sequencer, path_list=path_list
    )