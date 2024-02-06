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
        if (_ := session.get_seq_request(experiment_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        unpooled_libraries, _ = session.get_libraries(experiment_id=experiment_id, limit=None)

    unpooled_libraries = [library for library in unpooled_libraries if not library.is_pooled()]
    
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
        

@pooling_form_htmx.route("<int:experiment_id>/check_indices", methods=["POST"])
@login_required
def check_indices(experiment_id: int):
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
        
    pool_mapping_form = pooling_forms.PoolMappingForm()
    validated, pool_mapping_form = pool_mapping_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/pooling/pooling-3.html",
                seq_request=seq_request,
                pool_mapping_form=pool_mapping_form,
                experiment=experiment,
                **pool_mapping_form.prepare()
            )
        )
    
    df = pool_mapping_form.parse()
    
    barcode_check_form = pooling_forms.BarcodeCheckForm()
    context = barcode_check_form.prepare(df)

    return make_response(
        render_template(
            "components/popups/pooling/pooling-4.html",
            seq_request=seq_request,
            experiment=experiment,
            pool_mapping_form=pool_mapping_form,
            barcode_check_form=barcode_check_form,
            **context
        ), push_url=False
    )


@pooling_form_htmx.route("<int:experiment_id>/add_indices", methods=["POST"])
@login_required
def add_indices(experiment_id: int):
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    barcode_check_form = forms.BarcodeCheckForm()
    valid, barcode_check_form = barcode_check_form.custom_validate()
    if not valid:
        return make_response(
            render_template(
                "components/popups/pooling/pooling-4.html",
                seq_request=seq_request,
                experiment=experiment,
                barcode_check_form=barcode_check_form,
                **barcode_check_form.prepare()
            )
        )

    data = barcode_check_form.parse()
    pooling_table = data["pooling_table"]

    for _, row in pooling_table.iterrows():
        library = db.db_handler.get_library(row["id"])
        library.index_1_sequence = row["index_1"] if not pd.isna(row["index_1"]) else None
        library.index_2_sequence = row["index_2"] if not pd.isna(row["index_2"]) else None
        library.index_3_sequence = row["index_3"] if not pd.isna(row["index_3"]) else None
        library.index_4_sequence = row["index_4"] if not pd.isna(row["index_4"]) else None
        library.adapter = row["adapter"] if not pd.isna(row["adapter"]) else None
        library = db.db_handler.update_library(library)

    n_pools = 0
    for pool_label, _df in pooling_table.groupby("pool"):
        pool_label = str(pool_label)
        logger.debug(pool_label)
        logger.debug(_df[["sample_name", "library_type"]])
        pool = db.db_handler.create_pool(
            name=pool_label,
            owner_id=current_user.id,
            experiment_id=experiment_id,
            contact_name=_df["contact_person_name"].iloc[0],
            contact_email=_df["contact_person_email"].iloc[0],
            contact_phone=_df["contact_person_phone"].iloc[0],
        )

        for _, row in _df.iterrows():
            library = db.db_handler.get_library(int(row["id"]))
            library.pool_id = pool.id
            library = db.db_handler.update_library(library)

        n_pools += 1

    if experiment is not None:
        db.db_handler.link_experiment_seq_request(
            experiment_id=experiment.id
        )
    
    flash(f"Created and indexed {n_pools} succefully from request '{seq_request.name}'", "success")
    logger.debug(f"Created and indexed {n_pools} succefully from request '{seq_request.name}' [{seq_request.id}]")

    if experiment is not None:
        return make_response(
            redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        )

    return make_response(
        redirect=url_for("seq_requests_page.seq_request_page", experiment_id=seq_request.id),
    )