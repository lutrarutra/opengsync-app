import json
from datetime import datetime

import pandas as pd

from flask import Blueprint, request, Response, url_for
from flask_htmx import make_response

from opengsync_db import models

from ... import db
from ...core import wrappers, exceptions
from ...tools import ExcelWriter
from ...forms.workflows import billing as wff


billing_workflow = Blueprint("billing_workflow", __name__, url_prefix="/workflows/billing/")

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


@wrappers.resource_route(billing_workflow, methods=["GET"], db=db)
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
    
    pool_data = {
        "experiment_name": [],
        "lanes": [],
        "pool_name": [],
        "pool_type": [],
        "workflow": [],
        "num_m_reads_loaded": [],
        "lane_share": [],
        "flowcell_share": [],
        "num_libraries": [],
        "group": [],
        "contact_name": [],
        "contact_email": [],
        "billing_name": [],
        "billing_email": [],
        "billing_code": [],
        "lab_prep": [],
        "num_m_reads_requested": [],
        "lab_contact_name": [],
        "lab_contact_email": [],
        "pool_id": [],
        "info": [],
    }

    experiment_data = {
        "experiment_name": [],
        "workflow": [],
        "flow_cell_type": [],
        "max_m_reads": [],
        "max_m_reads_per_lane": [],
        "num_lanes": [],
        "num_pools": [],
        "read_config": [],
    }
    
    lane_data = {
        "experiment_name": [],
        "lane": [],
        "num_m_reads_loaded": [],
        "num_pools": [],
        "pools": [],
    }

    for experiment in experiments:
        experiment_data["experiment_name"].append(experiment.name)
        experiment_data["workflow"].append(experiment.workflow.name)
        experiment_data["flow_cell_type"].append(experiment.flowcell_type.name)
        experiment_data["max_m_reads"].append(experiment.flowcell_type.max_m_reads)
        experiment_data["max_m_reads_per_lane"].append(experiment.flowcell_type.max_m_reads_per_lane)
        experiment_data["num_pools"].append(len(experiment.pools))
        experiment_data["read_config"].append(experiment.read_config)
        experiment_data["num_lanes"].append(experiment.num_lanes)

        lane_loaded_reads = {}
        flowcell_loaded_reads = 0
        for lane in experiment.lanes:
            lane_data["experiment_name"].append(experiment.name)
            lane_data["lane"].append(lane.number)
            num_m_reads_loaded = 0
            lane_data["num_pools"].append(len(lane.pool_links))
            pools = []
            for link in lane.pool_links:
                pools.append(link.pool.name)
                if link.num_m_reads is not None:
                    num_m_reads_loaded += link.num_m_reads
                    flowcell_loaded_reads += link.num_m_reads
                else:
                    num_m_reads_loaded = None
                    break
            lane_data["num_m_reads_loaded"].append(num_m_reads_loaded or "")
            lane_data["pools"].append(", ".join(pools))
            lane_loaded_reads[lane.number] = num_m_reads_loaded

        for pool in experiment.pools:
            info = ""
            pool_data["pool_id"].append(pool.id)
            pool_data["pool_name"].append(pool.name)
            pool_data["pool_type"].append(pool.type.name)
            num_m_reads_loaded = 0
            lane_share = {}
            for link in pool.lane_links:
                if link.num_m_reads is not None:
                    num_m_reads_loaded += link.num_m_reads
                    lane_share[link.lane_num] = f"{link.num_m_reads / lane_loaded_reads[link.lane_num]:.3%}"
                else:
                    num_m_reads_loaded = None
                    info += "⚠️ Some lanes are missing number of loaded reads "
                    break
            
            pool_data["lane_share"].append(lane_share or "")
            
            if num_m_reads_loaded is not None:
                flowcell_share = (num_m_reads_loaded / flowcell_loaded_reads)
                pool_data["flowcell_share"].append(f"{flowcell_share:.3%}")
            else:
                pool_data["flowcell_share"].append("")
            
            contact = None
            billing_code = None
            if (seq_request := pool.seq_request) is None:
                if len(pool.libraries) > 0:
                    seq_request = pool.libraries[0].seq_request
                    for library in pool.libraries:
                        if library.seq_request != seq_request:
                            seq_request = None
                            break
                        
            if seq_request is not None:
                contact = seq_request.contact_person
                billing_code = seq_request.billing_code
                pool_data["group"].append(seq_request.group.name if seq_request.group else "")
            else:
                pool_data["group"].append("")

            if seq_request is None:
                info += "⚠️ Libraries in pool are from different requests "
                
            pool_data["workflow"].append(experiment.workflow.name)
            pool_data["contact_name"].append(contact.name if contact else "")
            pool_data["contact_email"].append(contact.email if contact else "")
            pool_data["billing_name"].append(seq_request.billing_contact.name if seq_request else "")
            pool_data["billing_email"].append(seq_request.billing_contact.email if seq_request else "")
            pool_data["billing_code"].append(billing_code or "")
            pool_data["num_m_reads_loaded"].append(num_m_reads_loaded or "")
            pool_data["num_m_reads_requested"].append(pool.num_m_reads_requested or 0)
            pool_data["num_libraries"].append(pool.num_libraries)
            pool_data["lab_contact_name"].append(pool.contact.name if pool.contact else "")
            pool_data["lab_contact_email"].append(pool.contact.email if pool.contact else "")
            pool_data["lab_prep"].append(pool.lab_prep.name if pool.lab_prep else "")
            pool_data["experiment_name"].append(experiment.name)
            pool_data["lanes"].append(", ".join(str(link.lane_num) for link in pool.lane_links))
            pool_data["info"].append(info)

    
    pools_df = pd.DataFrame(pool_data).sort_values(by=["experiment_name", "lanes"], ascending=[False, True]).reset_index(drop=True)
    lanes_df = pd.DataFrame(lane_data).sort_values(by=["experiment_name", "lane"], ascending=[False, True]).reset_index(drop=True)
    experiments_df = pd.DataFrame(experiment_data).sort_values(by=["experiment_name"], ascending=False).reset_index(drop=True)
    experiments_df["loaded_m_reads"] = ""

    for experiment in experiments:
        experiment_loaded_reads = sum(pools_df.loc[
            (pools_df["experiment_name"] == experiment.name) & (pools_df["num_m_reads_loaded"] != ""), "num_m_reads_loaded"
        ])
        experiments_df.loc[experiments_df["experiment_name"] == experiment.name, "loaded_m_reads"] = experiment_loaded_reads
        if experiment_loaded_reads > experiment.workflow.flow_cell_type.max_m_reads:
            pools_df.loc[pools_df["experiment_name"] == experiment.name, "info"] += "⚠️ Total loaded reads for experiment exceeds flow cell capacity "
        elif experiment_loaded_reads < experiment.workflow.flow_cell_type.max_m_reads:
            pools_df.loc[pools_df["experiment_name"] == experiment.name, "info"] += "⚠️ Total loaded reads for experiment is below flow cell capacity "

    pools_df["info"] = pools_df["info"].str.strip()
    file_name = f"billing_{datetime.now().strftime('%Y%m%d')}.xlsx"

    ew = ExcelWriter({
        "pools": pools_df,
        "experiments": experiments_df,
        "lanes": lanes_df
    })
    ew.apply_header_style(sheet_name=None)
    ew.apply_body_style(sheet_name=None)
    ew.apply_column_width(sheet_name=None, max_width=50)
    ew.apply_alternating_colors(sheet_name=None, column="experiment_name", primary_color="a4cbfa")
        
    return Response(
        ew.get_bytes(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )
