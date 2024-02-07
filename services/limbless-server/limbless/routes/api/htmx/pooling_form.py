from typing import TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, request, abort, Response
from flask_htmx import make_response
from flask_login import login_required

import pandas as pd

from .... import db, logger, models
from ....forms import pooling as pooling_forms
from ....core.DBSession import DBSession
from ....categories import HttpResponse

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user

pooling_form_htmx = Blueprint("pooling_form_htmx", __name__, url_prefix="/api/pooling_form/")


@pooling_form_htmx.route("<int:experiment_id>/download_pooling_template", methods=["GET"])
@login_required
def download_pooling_template(experiment_id: int):
    with DBSession(db.db_handler) as session:
        if (_ := session.get_experiment(experiment_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        unpooled_libraries, _ = session.get_libraries(experiment_id=experiment_id, limit=None, pooled=False)
    
    filename = f"pooling_template_{experiment_id}.tsv"

    data = {
        "id": [],
        "library_name": [],
        "library_type": [],
        "pool": [],
        "index_kit": [],
        "adapter": [],
        "index_1": [],
        "index_2": [],
        "index_3": [],
        "index_4": [],
        "library_volume": [],
        "library_concentration": [],
        "library_total_size": [],
    }
    for library in unpooled_libraries:
        if not library.is_pooled():
            data["id"].append(library.id)
            data["library_name"].append(library.name)
            data["library_type"].append(library.type.value.description)
            data["pool"].append("")
            data["index_kit"].append("")
            data["adapter"].append("")
            data["index_1"].append("")
            data["index_2"].append("")
            data["index_3"].append("")
            data["index_4"].append("")
            data["library_volume"].append("")
            data["library_concentration"].append("")
            data["library_total_size"].append("")

    df = pd.DataFrame(data).sort_values(by=["library_type", "library_name"])

    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


@pooling_form_htmx.route("<int:experiment_id>/get_pooling_form", methods=["GET"])
@login_required
def get_pooling_form(experiment_id: int):
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    return pooling_forms.PoolingInputForm().make_response(
        experiment=experiment
    )


@pooling_form_htmx.route("<int:experiment_id>/parse_pooling_form", methods=["POST"])
@login_required
def parse_pooling_form(experiment_id: int):
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
        
    return pooling_forms.PoolingInputForm(request.form | request.files).process_request(
        experiment=experiment
    )


@pooling_form_htmx.route("<int:experiment_id>/map_index_kits", methods=["POST"])
@login_required
def map_index_kits(experiment_id: int):
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
        
    return pooling_forms.IndexKitMappingForm(request.form).process_request(
        experiment=experiment
    )
        

@pooling_form_htmx.route("<int:experiment_id>/map_pools", methods=["POST"])
@login_required
def map_pools(experiment_id: int):
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
        
    return pooling_forms.PoolMappingForm(request.form).process_request(
        experiment=experiment
    )


@pooling_form_htmx.route("<int:experiment_id>/add_indices", methods=["POST"])
@login_required
def add_indices(experiment_id: int):
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    return pooling_forms.BarcodeCheckForm(request.form).process_request(
        experiment=experiment, user=current_user
    )
