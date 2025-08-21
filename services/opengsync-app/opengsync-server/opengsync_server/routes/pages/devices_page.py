from flask import Blueprint, render_template, url_for, abort

from opengsync_db import models
from opengsync_db.categories import UserRole, HTTPResponse

from ... import forms, db
from ...core import wrappers
devices_page_bp = Blueprint("devices_page", __name__)


@wrappers.page_route(devices_page_bp, db=db)
def devices(current_user: models.User):
    if current_user.role != UserRole.ADMIN:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sequencer_form = forms.models.SequencerForm()
    return render_template("devices_page.html", form=sequencer_form,)


@wrappers.page_route(devices_page_bp, db=db)
def sequencer(current_user: models.User, sequencer_id: int):
    if current_user.role != UserRole.ADMIN:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (sequencer := db.sequencers.get(sequencer_id)) is None:
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