import os
from typing import TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, abort, request, jsonify
from flask_htmx import make_response
from flask_login import login_required

from .... import db, forms, logger, models, PAGE_LIMIT
from ....categories import HttpResponse, ExperimentStatus
from ....core.DBSession import DBSession

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
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    with DBSession(db.db_handler) as session:
        experiments, n_pages = session.get_experiments(
            limit=PAGE_LIMIT, offset=offset, sort_by=sort_by, descending=descending
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
        return abort(HttpResponse.FORBIDDEN.value.id)

    return forms.ExperimentForm(formdata=request.form).process_request()


@experiments_htmx.route("<int:experiment_id>/edit", methods=["POST"])
@login_required
def edit(experiment_id: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    return forms.ExperimentForm(formdata=request.form).process_request(
        experiment=experiment
    )


@experiments_htmx.route("delete/<int:experiment_id>", methods=["POST"])
@login_required
def delete(experiment_id: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not experiment.is_deleteable():
        return abort(HttpResponse.FORBIDDEN.value.id)

    db.db_handler.delete_experiment(experiment_id)

    logger.debug(f"Deleted experiment on flowcell '{experiment.flowcell}'")
    flash(f"Deleted experiment on flowcell '{experiment.flowcell}'.", "success")
    
    return make_response(
        redirect=url_for("experiments_page.experiments_page"),
    )


@experiments_htmx.route("<int:experiment_id>/add_seq_request/<int:seq_request_id>", methods=["POST"])
@login_required
def add_seq_request(experiment_id: int, seq_request_id: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not experiment.is_editable():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    # TODO: check if it is already linked, shouldnt be, but still
    
    db.db_handler.link_experiment_seq_request(
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
    )

    logger.debug(f"Added request '{seq_request.name}' to experiment (id='{experiment_id}')")
    flash(f"Added request '{seq_request.name}' to experiment.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment_id),
        push_url=False
    )


@experiments_htmx.route("<int:experiment_id>/add_pool/<int:pool_id>/<int:lane>", methods=["POST"])
@login_required
def add_pool(experiment_id: int, pool_id: int, lane: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if (pool := db.db_handler.get_pool(pool_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if lane > experiment.num_lanes or lane < 1:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if not experiment.is_editable():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    db.db_handler.link_experiment_pool(
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
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if (pool := db.db_handler.get_pool(pool_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if lane > experiment.num_lanes or lane < 1:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if not experiment.is_editable():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    db.db_handler.unlink_experiment_pool(
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


@experiments_htmx.route("<int:experiment_id>/remove_seq_request", methods=["DELETE"])
@login_required
def remove_seq_request(experiment_id: int):
    if (request_id := request.args.get("request_id", None)) is not None:
        try:
            seq_request_id = int(request_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
    else:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not experiment.is_editable():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    db.db_handler.unlink_experiment_seq_request(
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
    )

    logger.debug(f"Removed request '{seq_request.name}' from experiment (id='{experiment_id}')")
    flash(f"Removed request '{seq_request.name}' from experiment.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        push_url=False
    )


@experiments_htmx.route("<int:experiment_id>/submit_experiment", methods=["POST"])
@login_required
def submit_experiment(experiment_id: int):
    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if not experiment.is_submittable():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        experiment.status_id = ExperimentStatus.SEQUENCING.value.id
        session.update_experiment(experiment)

    logger.info(f"Submitted experiment on flowcell '{experiment.flowcell}'")
    flash(f"Submitted experiment on flowcell '{experiment.flowcell}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
    )


@experiments_htmx.route("<int:experiment_id>/complete_experiment", methods=["POST"])
@login_required
def complete_experiment(experiment_id: int):
    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
    return forms.CompleteExperimentForm(formdata=request.form).process_request(
        experiment=experiment, user=current_user
    )


@experiments_htmx.route("<int:experiment_id>/upload_file", methods=["POST"])
@login_required
def upload_file(experiment_id: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    return forms.ExperimentFileForm(experiment_id=experiment_id, formdata=request.form | request.files).process_request(
        experiment=experiment, user=current_user
    )


@experiments_htmx.route("<int:experiment_id>/delete_file/<int:file_id>", methods=["DELETE"])
@login_required
def delete_file(experiment_id: int, file_id: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    if (experiment := db.db_handler.get_experiment(experiment_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if (file := db.db_handler.get_file(file_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    db.db_handler.remove_file_from_experiment(experiment_id=experiment.id, file_id=file_id)
    if os.path.exists(file.path):
        os.remove(file.path)

    logger.debug(f"Deleted file '{file.name}' from experiment (id='{experiment_id}')")
    flash(f"Deleted file '{file.name}' from experiment.", "success")
    return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))


@experiments_htmx.route("<int:experiment_id>/get_graph", methods=["GET"])
@login_required
def get_graph(experiment_id: int):
    if not current_user.is_insider():
        return abort(HttpResponse.FORBIDDEN.value.id)
    
    LINK_WIDTH_UNIT = 1
    
    with DBSession(db.db_handler) as session:
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
    
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
                            "name": f"{library.type.value.description}",
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