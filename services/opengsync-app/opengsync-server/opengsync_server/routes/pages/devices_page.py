from flask import Blueprint, render_template, url_for, abort
from flask_login import current_user

from opengsync_db.categories import UserRole, HTTPResponse
from ... import forms, db, page_route

devices_page_bp = Blueprint("devices_page", __name__)


@page_route(devices_page_bp, db=db)
def devices():
    if current_user.role != UserRole.ADMIN:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sequencer_form = forms.models.SequencerForm()
    return render_template("devices_page.html", form=sequencer_form,)


@page_route(devices_page_bp, db=db)
def sequencer(sequencer_id: int):
    if current_user.role != UserRole.ADMIN:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (sequencer := db.get_sequencer(sequencer_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    sequencer_form = forms.models.SequencerForm(sequencer=sequencer)

    path_list = [
        ("Devices", url_for("devices_page.devices")),
        (f"Device {sequencer.id}", ""),
    ]
    return render_template(
        "device_page.html", form=sequencer_form,
        sequencer=sequencer, path_list=path_list
    )