import os
from typing import TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, abort, request, jsonify, current_app
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT
from limbless_db.categories import HTTPResponse, ExperimentStatus
from .... import db, forms, logger

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

experiments_htmx = Blueprint("experiments_htmx", __name__, url_prefix="/api/experiments/")


@experiments_htmx.route("get/<int:page>")
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Experiment.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    with DBSession(db) as session:
        experiments, n_pages = session.get_experiments(
            offset=offset, sort_by=sort_by, descending=descending
        )

    return make_response(
        render_template(
            "components/tables/experiment.html",
            experiments=experiments,
            experiments_n_pages=n_pages, experiments_active_page=page,
            experiments_current_sort=sort_by, experiments_current_sort_order=order
        ), push_url=False
    )


@experiments_htmx.route("create", methods=["POST"])
@login_required
def create():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    return forms.ExperimentForm(formdata=request.form).process_request()


@experiments_htmx.route("<int:experiment_id>/edit", methods=["POST"])
@login_required
def edit(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.ExperimentForm(formdata=request.form).process_request(
        experiment=experiment
    )


@experiments_htmx.route("delete/<int:experiment_id>", methods=["DELETE"])
@login_required
def delete(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not experiment.is_deleteable():
        return abort(HTTPResponse.FORBIDDEN.id)

    db.delete_experiment(experiment_id)

    logger.debug(f"Deleted experiment on flowcell '{experiment.flowcell_id}'")
    flash(f"Deleted experiment on flowcell '{experiment.flowcell_id}'.", "success")
    
    return make_response(
        redirect=url_for("experiments_page.experiments_page"),
    )


@experiments_htmx.route("<int:experiment_id>/add_pool/<int:pool_id>/<int:lane>", methods=["POST"])
@login_required
def add_pool(experiment_id: int, pool_id: int, lane: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if lane > experiment.num_lanes or lane < 1:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if not experiment.is_editable():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    db.link_experiment_pool(
        experiment_id=experiment_id,
        pool_id=pool.id,
        lane=lane,
    )

    logger.debug(f"Added pool '{pool.name}' to experiment (id='{experiment_id}') on lane '{lane}'")
    flash(f"Added pool '{pool.name}' to experiment on lane '{lane}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        push_url=False
    )


@experiments_htmx.route("<int:experiment_id>/remove_pool/<int:pool_id>/<int:lane>", methods=["DELETE"])
@login_required
def remove_pool(experiment_id: int, pool_id: int, lane: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if lane > experiment.num_lanes or lane < 1:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if not experiment.is_editable():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    db.unlink_experiment_pool(
        experiment_id=experiment_id,
        pool_id=pool_id,
        lane=lane,
    )

    logger.debug(f"Removed pool '{pool.name}' from experiment  (id='{experiment_id}') on lane '{lane}'")
    flash(f"Removed pool '{pool.name}' from experiment on lane '{lane}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        push_url=False
    )


@experiments_htmx.route("<int:experiment_id>/submit_experiment", methods=["POST"])
@login_required
def submit_experiment(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if not experiment.is_submittable():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        experiment.status_id = ExperimentStatus.SEQUENCING.id
        session.update_experiment(experiment)

    logger.info(f"Submitted experiment on flowcell '{experiment.flowcell_id}'")
    flash(f"Submitted experiment on flowcell '{experiment.flowcell_id}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
    )


@experiments_htmx.route("<int:experiment_id>/complete_experiment", methods=["POST"])
@login_required
def complete_experiment(experiment_id: int):
    with DBSession(db) as session:
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
    return forms.CompleteExperimentForm(formdata=request.form).process_request(
        experiment=experiment, user=current_user
    )


@experiments_htmx.route("<int:experiment_id>/upload_file", methods=["POST"])
@login_required
def upload_file(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.ExperimentAttachmentForm(experiment_id=experiment_id, formdata=request.form | request.files).process_request(
        experiment=experiment, user=current_user
    )


@experiments_htmx.route("<int:experiment_id>/delete_file/<int:file_id>", methods=["DELETE"])
@login_required
def delete_file(experiment_id: int, file_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (file := db.get_file(file_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    db.remove_file_from_experiment(experiment_id=experiment.id, file_id=file_id)
    filepath = os.path.join(current_app.config["MEDIA_FOLDER"], file.path)
    if os.path.exists(filepath):
        os.remove(filepath)

    logger.info(f"Deleted file '{file.name}' from experiment (id='{experiment_id}')")
    flash(f"Deleted file '{file.name}' from experiment.", "success")
    return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))


@experiments_htmx.route("<int:experiment_id>/add_comment", methods=["POST"])
@login_required
def add_comment(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.ExperimentCommentForm(experiment_id=experiment_id, formdata=request.form).process_request(user=current_user, experiment=experiment)


@experiments_htmx.route("<int:experiment_id>/get_graph", methods=["GET"])
@login_required
def get_graph(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    LINK_WIDTH_UNIT = 1
    
    with DBSession(db) as session:
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
    
        graph = {
            "nodes": [],
            "links": [],
        }

        experiment_node = {
            "node": 0,
            "name": f"Experiment {experiment.id}",
        }
        graph["nodes"].append(experiment_node)
        idx = 1
        
        library_nodes: dict[int, int] = {}
        pool_nodes: dict[int, int] = {}
        seq_request_nodes: dict[int, int] = {}
        lane_nodes: dict[int, int] = {}
        lane_widths: dict[int, float] = {}

        experiment_lanes = session.get_lanes_in_experiment(experiment_id)

        for lane in range(1, experiment.num_lanes + 1):
            lane_libraries_count = 0
            lane_widths[lane] = 0
            if lane not in lane_nodes.keys():
                lane_node = {
                    "node": idx,
                    "name": f"Lane {lane}",
                }
                graph["nodes"].append(lane_node)
                lane_nodes[lane] = idx
                lane_node_idx = idx
                idx += 1
            else:
                lane_node_idx = lane_nodes[lane]

            for pool_link in experiment.pool_links:
                if pool_link.lane != lane:
                    continue
                
                if pool_link.pool.id not in pool_nodes.keys():
                    pool_node = {
                        "node": idx,
                        "name": f"{pool_link.pool.name}",
                    }
                    graph["nodes"].append(pool_node)
                    pool_nodes[pool_link.pool.id] = idx
                    pool_node_idx = idx
                    idx += 1
                else:
                    pool_node_idx = pool_nodes[pool_link.pool.id]

                for library in pool_link.pool.libraries:
                    lane_libraries_count += 1
                    if library.seq_request_id not in seq_request_nodes.keys():
                        seq_request_node = {
                            "node": idx,
                            "name": f"{library.seq_request.name}",
                        }
                        graph["nodes"].append(seq_request_node)
                        seq_request_nodes[library.seq_request.id] = idx
                        seq_request_node_idx = idx
                        idx += 1
                    else:
                        seq_request_node_idx = seq_request_nodes[library.seq_request.id]
                    
                    if library.id not in library_nodes.keys():
                        library_node = {
                            "node": idx,
                            "name": f"{library.type.description}",
                        }
                        graph["nodes"].append(library_node)
                        library_nodes[library.id] = idx
                        graph["links"].append({
                            "source": seq_request_node_idx,
                            "target": idx,
                            "value": LINK_WIDTH_UNIT,
                        })
                        graph["links"].append({
                            "source": idx,
                            "target": pool_node_idx,
                            "value": LINK_WIDTH_UNIT,
                        })
                        idx += 1
                
                graph["links"].append({
                    "source": pool_node_idx,
                    "target": lane_node_idx,
                    "value": LINK_WIDTH_UNIT * len(pool_link.pool.libraries) / len(experiment_lanes[pool_link.pool_id]),
                })
                lane_widths[lane] += LINK_WIDTH_UNIT * len(pool_link.pool.libraries) / len(experiment_lanes[pool_link.pool_id])

            graph["links"].append({
                "source": lane_node_idx,
                "target": experiment_node["node"],
                "value": lane_widths[lane],
            })

    return make_response(
        jsonify(graph)
    )