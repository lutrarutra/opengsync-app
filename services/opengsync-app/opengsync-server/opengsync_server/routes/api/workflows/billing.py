import json
from datetime import datetime
from io import BytesIO

import pandas as pd

from flask import Blueprint, request, Response, url_for
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import PoolStatus, PoolType, AccessType

from .... import db
from ....core import wrappers, exceptions
from ....forms.workflows import billing as wff



billing_workflow = Blueprint("billing_workflow", __name__, url_prefix="/api/workflows/billing/")

@wrappers.htmx_route(billing_workflow, db=db)
def begin(current_user: models.User) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    return wff.SelectExperimentsForm().make_response()


@wrappers.htmx_route(billing_workflow, db=db, methods=["POST"])
def select(current_user: models.User) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    form = wff.SelectExperimentsForm(formdata=request.form)
    if not form.validate():
        return form.make_response()
    
    experiments = form.selected_experiments
    return make_response(redirect=url_for("billing_workflow.download", experiment_ids={json.dumps([e.id for e in experiments])}))


@wrappers.htmx_route(billing_workflow, methods=["GET"], db=db)
def download(current_user: models.User) -> Response:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    experiment_ids = request.args.get("experiment_ids")
    if experiment_ids is None:
        raise exceptions.BadRequestException("No experiment ids provided")
    try:
        experiment_ids = json.loads(experiment_ids)
        experiments: list[models.Experiment] = []
        for experiment_id in experiment_ids:
            if (experiment := db.experiments.get(int(experiment_id))) is None:
                raise exceptions.NotFoundException(f"Experiment with id {experiment_id} not found")
            experiments.append(experiment)
    except ValueError:
        raise exceptions.BadRequestException("Invalid experiment ids")
    
    data = {
        "pool_id": [],
        "pool_name": [],
        "pool_type": [],
        "flowcell_share": [],
        "num_m_reads_loaded": [],
        "num_m_reads_requested": [],
        "num_libraries": [],
        "contact_name": [],
        "contact_email": [],
        "lab_prep": [],
        "experiment_name": [],
        "lanes": [],
        "billing_code": [],
        "lab_contact_name": [],
        "lab_contact_email": [],
        "info": [],
    }
    for experiment in experiments:
        for pool in experiment.pools:
            info = ""
            data["pool_id"].append(pool.id)
            data["pool_name"].append(pool.name)
            data["pool_type"].append(pool.type.name)
            num_m_reads_loaded = 0
            for link in pool.lane_links:
                if link.num_m_reads is not None:
                    num_m_reads_loaded += link.num_m_reads
                else:
                    num_m_reads_loaded = None
                    info += "⚠️ Some lanes are missing number of loaded reads "
                    break
            
            if num_m_reads_loaded is not None:
                flowcell_share = (num_m_reads_loaded / experiment.workflow.flow_cell_type.max_m_reads)
                data["flowcell_share"].append(f"{flowcell_share:.3%}")
            else:
                data["flowcell_share"].append("")
            
            contact = None
            billing_code = None
            if len(pool.libraries) > 0:
                seq_request = pool.libraries[0].seq_request
                for library in pool.libraries:
                    if library.seq_request != seq_request:
                        seq_request = None
                        break
                    
                if seq_request is not None:
                    contact = seq_request.contact_person
                    billing_code = seq_request.billing_code

                if seq_request is None:
                    info += "⚠️ Libraries in pool are from different requests "
                
            data["contact_name"].append(contact.name if contact else "")
            data["contact_email"].append(contact.email if contact else "")
            data["billing_code"].append(billing_code or "")
            data["num_m_reads_loaded"].append(num_m_reads_loaded or "")
            data["num_m_reads_requested"].append(pool.num_m_reads_requested or 0)
            data["num_libraries"].append(pool.num_libraries)
            data["lab_contact_name"].append(pool.contact.name if pool.contact else "")
            data["lab_contact_email"].append(pool.contact.email if pool.contact else "")
            data["lab_prep"].append(pool.lab_prep.name if pool.lab_prep else "")
            data["experiment_name"].append(experiment.name)
            data["lanes"].append(", ".join(str(link.lane_num) for link in pool.lane_links))
            data["info"].append(info)

    
    pools_df = pd.DataFrame(data)

    for experiment in experiments:
        experiment_loaded_reads = sum(pools_df.loc[
            (pools_df["experiment_name"] == experiment.name) & (pools_df["num_m_reads_loaded"] != ""), "num_m_reads_loaded"
        ])
        if experiment_loaded_reads > experiment.workflow.flow_cell_type.max_m_reads:
            pools_df.loc[pools_df["experiment_name"] == experiment.name, "info"] += "⚠️ Total loaded reads for experiment exceeds flow cell capacity "
        elif experiment_loaded_reads < experiment.workflow.flow_cell_type.max_m_reads:
            pools_df.loc[pools_df["experiment_name"] == experiment.name, "info"] += "⚠️ Total loaded reads for experiment is below flow cell capacity "

    pools_df["info"] = pools_df["info"].str.strip()
    file_name = f"billing_{datetime.now().strftime('%Y%m%d')}.xlsx"

    bytes_io = BytesIO()
    with pd.ExcelWriter(bytes_io, engine="openpyxl") as writer:  # type: ignore
        pools_df.to_excel(writer, sheet_name="pools", index=True)

    bytes_io.seek(0)
        
    return Response(
        bytes_io, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )
