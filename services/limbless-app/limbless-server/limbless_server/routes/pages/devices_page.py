from flask import Blueprint, render_template, url_for, abort
from flask_login import login_required, current_user

from limbless_db import DBSession
from limbless_db.core.categories import UserRole, HttpResponse
from ... import forms, db

devices_page_bp = Blueprint("devices_page", __name__)


@devices_page_bp.route("/devices")
@login_required
def devices_page():
    if current_user.role != UserRole.ADMIN:
        return abort(HttpResponse.FORBIDDEN.id)
    
    sequencer_form = forms.SequencerForm()
    with DBSession(db) as session:
        sequencers, n_pages = session.get_sequencers()

    return render_template(
        "devices_page.html", form=sequencer_form,
        sequencers=sequencers,
        sequencers_n_pages=n_pages, sequencers_active_page=0
    )


@devices_page_bp.route("/sequencers/<int:sequencer_id>", methods=["GET"])
@login_required
def sequencer_page(sequencer_id: int):
    if current_user.role != UserRole.ADMIN:
        return abort(HttpResponse.FORBIDDEN.id)
    
    if (sequencer := db.get_sequencer(sequencer_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)
    
    sequencer_form = forms.SequencerForm()
    sequencer_form.name.data = sequencer.name
    sequencer_form.ip_address.data = sequencer.ip

    path_list = [
        ("Devices", url_for("devices_page.devices_page")),
        (f"Device {sequencer.id}", ""),
    ]
    return render_template(
        "device_page.html", form=sequencer_form,
        sequencer=sequencer, path_list=path_list
    )