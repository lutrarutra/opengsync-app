from typing import TYPE_CHECKING

import pandas as pd

from flask import Blueprint, request, abort
from flask_login import login_required

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse

from .... import db, logger
from ....forms.workflows import check_barcode_clashes as wff
from ....forms import SelectSamplesForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

check_barcode_clashes_workflow = Blueprint("check_barcode_clashes_workflow", __name__, url_prefix="/api/workflows/check_barcode_clashes/")


@check_barcode_clashes_workflow.route("begin", methods=["GET"])
@db_session(db)
@login_required
def begin():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    form = SelectSamplesForm(
        workflow="check_barcode_clashes",
        select_lanes=True,
        select_pools=True,
        select_libraries=True,
    )

    return form.make_response()


@check_barcode_clashes_workflow.route("select", methods=["POST"])
@db_session(db)
@login_required
def select():
    form: SelectSamplesForm = SelectSamplesForm("check_barcode_clashes", formdata=request.form)

    if not form.validate():
        return form.make_response()
        
    library_data = {
        "library_id": [],
        "library_name": [],
        "sequence_i7": [],
        "sequence_i5": [],
    }

    for _, row in form.library_table.iterrows():
        if (library := db.get_library(int(row["id"]))) is None:
            logger.error(f"Library {library} not found in database")
            raise Exception("Library not found in database")
        
        for index in library.indices:
            library_data["library_id"].append(library.id)
            library_data["library_name"].append(library.name)
            library_data["sequence_i7"].append(index.sequence_i7)
            library_data["sequence_i5"].append(index.sequence_i5)

    for _, row in form.pool_table.iterrows():
        if (pool := db.get_pool(int(row["id"]))) is None:
            logger.error(f"Pool {pool} not found in database")
            raise Exception("Pool not found in database")

        for library in pool.libraries:
            for index in library.indices:
                library_data["library_id"].append(library.id)
                library_data["library_name"].append(library.name)
                library_data["sequence_i7"].append(index.sequence_i7)
                library_data["sequence_i5"].append(index.sequence_i5)

    for _, row in form.lane_table.iterrows():
        if (lane := db.get_lane(int(row["id"]))) is None:
            logger.error(f"Lane {lane} not found in database")
            raise Exception("Lane not found in database")

        for pool_link in lane.pool_links:
            for library in pool_link.pool.libraries:
                for index in library.indices:
                    library_data["library_id"].append(library.id)
                    library_data["library_name"].append(library.name)
                    library_data["sequence_i7"].append(index.sequence_i7)
                    library_data["sequence_i5"].append(index.sequence_i5)
        
    libraries_df = pd.DataFrame(library_data)
    return wff.CheckBarcodeClashesForm(libraries_df).process_request()


@check_barcode_clashes_workflow.route("check_experiment_barcode_clashes/<int:experiment_id>", methods=["GET"])
@db_session(db)
@login_required
def check_experiment_barcode_clashes(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    library_data = {
        "library_id": [],
        "library_name": [],
        "lane": [],
        "lane_id": [],
        "pool": [],
        "sequence_i7": [],
        "sequence_i5": [],
    }

    for lane in experiment.lanes:
        for pool_link in lane.pool_links:
            for library in pool_link.pool.libraries:
                for index in library.indices:
                    library_data["library_id"].append(library.id)
                    library_data["library_name"].append(library.name)
                    library_data["lane"].append(lane.number)
                    library_data["lane_id"].append(lane.id)
                    library_data["pool"].append(pool_link.pool.name)
                    library_data["sequence_i7"].append(index.sequence_i7)
                    library_data["sequence_i5"].append(index.sequence_i5)

    library_df = pd.DataFrame(library_data)
    return wff.CheckBarcodeClashesForm(library_df, groupby="lane").process_request()


@check_barcode_clashes_workflow.route("check_seq_request_barcode_clashes/<int:seq_request_id>", methods=["GET"])
@db_session(db)
@login_required
def check_seq_request_barcode_clashes(seq_request_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    library_data = {
        "library_id": [],
        "library_name": [],
        "pool": [],
        "pool_id": [],
        "sequence_i7": [],
        "sequence_i5": [],
    }

    for pool in seq_request.pools:
        for library in pool.libraries:
            for index in library.indices:
                library_data["library_id"].append(library.id)
                library_data["library_name"].append(library.name)
                library_data["pool"].append(pool.name)
                library_data["pool_id"].append(pool.id)
                library_data["sequence_i7"].append(index.sequence_i7)
                library_data["sequence_i5"].append(index.sequence_i5)
            
    library_df = pd.DataFrame(library_data)
    return wff.CheckBarcodeClashesForm(library_df, groupby="pool").process_request()


