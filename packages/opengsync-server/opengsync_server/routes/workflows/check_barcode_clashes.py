import pandas as pd

from flask import Blueprint, request

from opengsync_db import models

from ... import db, logger
from ...forms.workflows import check_barcode_clashes as wff
from ...forms import SelectSamplesForm
from ...core import wrappers, exceptions

check_barcode_clashes_workflow = Blueprint("check_barcode_clashes_workflow", __name__, url_prefix="/workflows/check_barcode_clashes/")


@wrappers.htmx_route(check_barcode_clashes_workflow, db=db)
def begin(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    form = SelectSamplesForm(
        workflow="check_barcode_clashes",
        select_lanes=True,
        select_pools=True,
        select_libraries=True,
    )

    return form.make_response()


@wrappers.htmx_route(check_barcode_clashes_workflow, db=db, methods=["POST"])
def select():
    form: SelectSamplesForm = SelectSamplesForm("check_barcode_clashes", formdata=request.form)

    if not form.validate():
        return form.make_response()
        
    library_data = {
        "library_id": [],
        "library_name": [],
        "sequence_i7": [],
        "sequence_i5": [],
        "kit_i7_id": [],
        "kit_i5_id": [],
        "index_type_id": [],
    }

    for _, row in form.library_table.iterrows():
        if (library := db.libraries.get(int(row["id"]))) is None:
            logger.error(f"Library {library} not found in database")
            raise Exception("Library not found in database")
        
        for index in library.indices:
            library_data["library_id"].append(library.id)
            library_data["library_name"].append(library.name)
            library_data["sequence_i7"].append(index.sequence_i7)
            library_data["sequence_i5"].append(index.sequence_i5)
            library_data["kit_i7_id"].append(index.index_kit_i7_id)
            library_data["kit_i5_id"].append(index.index_kit_i5_id)
            library_data["index_type_id"].append(index.type.id)

    for _, row in form.pool_table.iterrows():
        if (pool := db.pools.get(int(row["id"]))) is None:
            logger.error(f"Pool {pool} not found in database")
            raise Exception("Pool not found in database")

        for library in pool.libraries:
            for index in library.indices:
                library_data["library_id"].append(library.id)
                library_data["library_name"].append(library.name)
                library_data["sequence_i7"].append(index.sequence_i7)
                library_data["sequence_i5"].append(index.sequence_i5)
                library_data["kit_i7_id"].append(index.index_kit_i7_id)
                library_data["kit_i5_id"].append(index.index_kit_i5_id)
                library_data["index_type_id"].append(index.type.id)

    for _, row in form.lane_table.iterrows():
        if (lane := db.lanes.get(int(row["id"]))) is None:
            logger.error(f"Lane {lane} not found in database")
            raise Exception("Lane not found in database")

        for pool_link in lane.pool_links:
            for library in pool_link.pool.libraries:
                for index in library.indices:
                    library_data["library_id"].append(library.id)
                    library_data["library_name"].append(library.name)
                    library_data["sequence_i7"].append(index.sequence_i7)
                    library_data["sequence_i5"].append(index.sequence_i5)
                    library_data["kit_i7_id"].append(index.index_kit_i7_id)
                    library_data["kit_i5_id"].append(index.index_kit_i5_id)
                    library_data["index_type_id"].append(index.type.id)
        
    libraries_df = pd.DataFrame(library_data)
    return wff.CheckBarcodeClashesForm(libraries_df).process_request()


@wrappers.htmx_route(check_barcode_clashes_workflow, db=db)
def check_experiment_barcode_clashes(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    library_data = {
        "library_id": [],
        "library_name": [],
        "lane": [],
        "lane_id": [],
        "pool": [],
        "sequence_i7": [],
        "sequence_i5": [],
        "kit_i7_id": [],
        "kit_i5_id": [],
        "index_type_id": [],
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
                    library_data["kit_i7_id"].append(index.index_kit_i7_id)
                    library_data["kit_i5_id"].append(index.index_kit_i5_id)
                    library_data["index_type_id"].append(index.type.id)

    library_df = pd.DataFrame(library_data)
    return wff.CheckBarcodeClashesForm(library_df, groupby="lane").process_request()


@wrappers.htmx_route(check_barcode_clashes_workflow, db=db)
def check_seq_request_barcode_clashes(current_user: models.User, seq_request_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    library_data = {
        "library_id": [],
        "library_name": [],
        "pool": [],
        "pool_id": [],
        "sequence_i7": [],
        "sequence_i5": [],
        "kit_i7_id": [],
        "kit_i5_id": [],
        "index_type_id": [],
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
                library_data["kit_i7_id"].append(index.index_kit_i7_id)
                library_data["kit_i5_id"].append(index.index_kit_i5_id)
                library_data["index_type_id"].append(index.type.id)

            
    library_df = pd.DataFrame(library_data)
    return wff.CheckBarcodeClashesForm(library_df, groupby="pool").process_request()
