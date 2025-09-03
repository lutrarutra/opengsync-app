import os
import json
from typing import Literal

import pandas as pd

from flask import Blueprint, url_for, render_template, flash, request
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import ExperimentStatus, ExperimentWorkFlow, ProjectStatus

from .... import db, forms, logger
from ....core.RunTime import runtime
from ....core import wrappers, exceptions

experiments_htmx = Blueprint("experiments_htmx", __name__, url_prefix="/api/hmtx/experiments/")


@wrappers.htmx_route(experiments_htmx, db=db)
def get(page: int = 0):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [ExperimentStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    if (workflow_in := request.args.get("workflow_id_in")) is not None:
        workflow_in = json.loads(workflow_in)
        try:
            workflow_in = [ExperimentWorkFlow.get(int(workflow)) for workflow in workflow_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(workflow_in) == 0:
            workflow_in = None

    experiments, n_pages = db.experiments.find(
        offset=offset, sort_by=sort_by, descending=descending,
        status_in=status_in, workflow_in=workflow_in, count_pages=True
    )

    return make_response(
        render_template(
            "components/tables/experiment.html",
            experiments=experiments,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            ExperimentStatus=ExperimentStatus, status_in=status_in,
            ExperimentWorkFlow=ExperimentWorkFlow, workflow_in=workflow_in
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db)
def get_form(current_user: models.User, form_type: Literal["create", "edit"]):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if form_type not in ["create", "edit"]:
        raise exceptions.BadRequestException()
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if form_type != "edit":
            raise exceptions.BadRequestException()
        
        if (experiment := db.experiments.get(experiment_id)) is None:
            raise exceptions.NotFoundException()
        
        return forms.models.ExperimentForm(form_type=form_type, experiment=experiment).make_response()

    # seq_request_id must be provided if form_type is "edit"
    if form_type == "edit":
        raise exceptions.BadRequestException()

    return forms.models.ExperimentForm(form_type=form_type, current_user=current_user).make_response()


@wrappers.htmx_route(experiments_htmx, db=db, methods=["POST"])
def create(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    return forms.models.ExperimentForm(formdata=request.form, form_type="create").process_request()


@wrappers.htmx_route(experiments_htmx, methods=["POST"], db=db)
def edit(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()

    return forms.models.ExperimentForm(formdata=request.form, form_type="edit").process_request(
        experiment=experiment
    )


@wrappers.htmx_route(experiments_htmx, methods=["DELETE"], db=db)
def delete(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if not experiment.is_deleteable():
        raise exceptions.NoPermissionsException()

    db.experiments.delete(experiment_id)

    logger.debug(f"Deleted experiment on flowcell '{experiment.name}'")
    flash(f"Deleted experiment on flowcell '{experiment.name}'.", "success")
    
    return make_response(
        redirect=url_for("experiments_page.experiments"),
    )


@wrappers.htmx_route(experiments_htmx, db=db, methods=["POST"])
def query(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name)) is None:
        raise exceptions.BadRequestException()

    results = db.experiments.query(word)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results, field_name=field_name,
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db)
def render_lane_sample_pooling_tables(current_user: models.User, experiment_id: int, file_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
        
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
        
    if (file := db.files.get(file_id)) is None:
        raise exceptions.NotFoundException()

    filepath = os.path.join(runtime.app.media_folder, file.path)
    df = pd.read_csv(filepath, sep="\t")

    if "lane" not in df.columns:
        target_molarity = df["target_molarity"].values[0]
        target_total_volume = df["target_total_volume"].values[0]
        pipet = df["pipet"].sum()
        eb_volume = target_total_volume - pipet
        return make_response(
            render_template(
                "components/experiment-pooling-ratios.html", experiment=experiment, df=df,
                target_molarity=target_molarity, target_total_volume=target_total_volume,
                pipet=pipet, eb_volume=eb_volume
            )
        )
    
    return make_response(
        render_template(
            "components/lane-pooling-ratios.html", experiment=experiment, df=df
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db)
def table_query(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (word := request.args.get("name", None)) is not None:
        field_name = "name"
    elif (word := request.args.get("id", None)) is not None:
        field_name = "id"
    else:
        raise exceptions.BadRequestException()
    
    if word is None:
        raise exceptions.BadRequestException()
    
    if (workflow_in := request.args.get("workflow_id_in")) is not None:
        workflow_in = json.loads(workflow_in)
        try:
            workflow_in = [ExperimentWorkFlow.get(int(workflow)) for workflow in workflow_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(workflow_in) == 0:
            workflow_in = None
    
    experiments = []
    if field_name == "name":
        experiments = db.experiments.query(word, workflow_in=workflow_in)
    elif field_name == "id":
        try:
            if (experiment := db.experiments.get(int(word))) is not None:
                experiments = [experiment]
                if workflow_in is not None and experiment.workflow not in workflow_in:
                    experiments = []
        except ValueError:
            pass

    return make_response(
        render_template(
            "components/tables/experiment.html",
            experiments=experiments, current_query=word, field_name=field_name,
            ExperimentWorkFlow=ExperimentWorkFlow, workflow_in=workflow_in
        )
    )
                     

@wrappers.htmx_route(experiments_htmx, db=db, methods=["POST"])
def lane_pool(current_user: models.User, experiment_id: int, pool_id: int, lane_num: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if lane_num > experiment.num_lanes or lane_num < 1:
        raise exceptions.BadRequestException()
    
    if (_ := db.lanes.get_experiment_lane(experiment_id=experiment_id, lane_num=lane_num)) is None:
        raise exceptions.NotFoundException()
    
    db.links.add_pool_to_lane(
        experiment_id=experiment_id,
        pool_id=pool_id,
        lane_num=lane_num
    )

    logger.debug(f"Added pool '{pool.name}' to experiment (id='{experiment_id}') on lane '{lane_num}'")
    flash(f"Added pool '{pool.name}' to lane '{lane_num}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment", experiment_id=experiment.id),
        push_url=False
    )


@wrappers.htmx_route(experiments_htmx, db=db, methods=["DELETE"])
def unlane_pool(current_user: models.User, experiment_id: int, pool_id: int, lane_num: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if (pool := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()
    
    if lane_num > experiment.num_lanes or lane_num < 1:
        raise exceptions.BadRequestException()
    
    if (_ := db.lanes.get_experiment_lane(experiment_id=experiment_id, lane_num=lane_num)) is None:
        raise exceptions.NotFoundException()
    
    db.links.remove_pool_from_lane(
        experiment_id=experiment_id,
        pool_id=pool_id,
        lane_num=lane_num,
    )

    logger.debug(f"Removed pool '{pool.name}' from lane '{lane_num}' (experiment_id='{experiment_id}')")
    flash(f"Removed pool '{pool.name}' from lane '{lane_num}'.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment", experiment_id=experiment.id),
        push_url=False
    )


@wrappers.htmx_route(experiments_htmx, db=db, methods=["GET", "POST"])
def comment_form(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        form = forms.comment.ExperimentCommentForm(experiment=experiment)
        return form.make_response()
    elif request.method == "POST":
        form = forms.comment.ExperimentCommentForm(experiment=experiment, formdata=request.form)
        return form.process_request(current_user)
    else:
        raise exceptions.MethodNotAllowedException()
    

@wrappers.htmx_route(experiments_htmx, db=db, methods=["GET", "POST"])
def file_form(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        form = forms.file.ExperimentAttachmentForm(experiment=experiment)
        return form.make_response()
    elif request.method == "POST":
        form = forms.file.ExperimentAttachmentForm(experiment=experiment, formdata=request.form | request.files)
        return form.process_request(current_user)
    else:
        raise exceptions.MethodNotAllowedException()


@wrappers.htmx_route(experiments_htmx, db=db, methods=["DELETE"])
def delete_file(current_user: models.User, experiment_id: int, file_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if (file := db.files.get(file_id)) is None:
        raise exceptions.NotFoundException()
    
    if file not in experiment.media_files:
        raise exceptions.BadRequestException()
    
    file_path = os.path.join(runtime.app.media_folder, file.path)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.files.delete(file_id=file.id)

    logger.info(f"Deleted file '{file.name}' from experiment (id='{experiment_id}')")
    flash(f"Deleted file '{file.name}' from experiment.", "success")
    return make_response(redirect=url_for("experiments_page.experiment", experiment_id=experiment.id))


@wrappers.htmx_route(experiments_htmx, db=db, methods=["POST"])
def add_comment(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    return forms.comment.ExperimentCommentForm(experiment=experiment, formdata=request.form).process_request(user=current_user)


@wrappers.htmx_route(experiments_htmx, db=db, methods=["DELETE"])
def remove_pool(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if (pool_id := request.args.get("pool_id")) is None:
        raise exceptions.BadRequestException()
    
    try:
        pool_id = int(pool_id)
    except ValueError:
        raise exceptions.BadRequestException()
    
    if (_ := db.pools.get(pool_id)) is None:
        raise exceptions.NotFoundException()

    db.links.unlink_pool_experiment(experiment_id=experiment_id, pool_id=pool_id)

    logger.info(f"Removed pool (id='{pool_id}') from experiment (id='{experiment_id}')")
    flash("Removed pool from experiment.", "success")

    return make_response(
        redirect=url_for("experiments_page.experiment", experiment_id=experiment.id),
    )
    

@wrappers.htmx_route(experiments_htmx, db=db)
def overview(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    LINK_WIDTH_UNIT = 1
    
    df = db.pd.get_experiment_libraries(experiment_id=experiment_id, include_indices=False, include_seq_request=True, collapse_lanes=False)

    if df.empty:
        return make_response(
            render_template(
                "components/plots/experiment_overview.html",
                links=[], nodes=[]
            )
        )
    nodes = []
    links = []

    experiment_node = {
        "node": 0,
        "name": experiment.name
    }
    nodes.append(experiment_node)
    node_idx = 1

    libraries = {}
    pools = {}
    lanes = {}
    lane_widths = {}
    for lane in df["lane"].unique():
        lane_node = {
            "node": node_idx,
            "name": f"Lane {lane}"
        }
        node_idx += 1
        nodes.append(lane_node)
        lanes[lane] = lane_node
        lane_widths[lane] = 0

    for (_, request_name), _df in df.groupby(["seq_request_id", "request_name"]):
        request_node = {
            "node": node_idx,
            "name": request_name
        }
        nodes.append(request_node)
        node_idx += 1
        for (pool_id, pool_name, lane), __df in _df.groupby(["pool_id", "pool_name", "lane"]):
            if pool_id not in pools.keys():
                pool_node = {
                    "node": node_idx,
                    "name": pool_name
                }
                node_idx += 1
                nodes.append(pool_node)
                pools[pool_id] = pool_node
            else:
                pool_node = pools[pool_id]

            width = __df.shape[0] / len(df[df["pool_id"] == pool_id]["lane"].unique())
            links.append({
                "source": pool_node["node"],
                "target": lanes[lane]["node"],
                "value": LINK_WIDTH_UNIT * width
            })
            lane_widths[lane] += width

            for i, row in __df.iterrows():
                if row["library_id"] not in libraries.keys():
                    library_node = {
                        "node": node_idx,
                        "name": row["library_type"].name
                    }
                    node_idx += 1
                    nodes.append(library_node)
                    libraries[row["library_id"]] = library_node
                    links.append({
                        "source": library_node["node"],
                        "target": pool_node["node"],
                        "value": LINK_WIDTH_UNIT
                    })
                    links.append({
                        "source": request_node["node"],
                        "target": library_node["node"],
                        "value": LINK_WIDTH_UNIT
                    })
                else:
                    library_node = libraries[row["library_id"]]

    for lane, _ in df.groupby("lane"):
        links.append({
            "source": lanes[lane]["node"],
            "target": experiment_node["node"],
            "value": LINK_WIDTH_UNIT * lane_widths[lane]
        })

    return make_response(
        render_template(
            "components/plots/experiment_overview.html",
            links=links, nodes=nodes
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db)
def get_pools(current_user: models.User, experiment_id: int, page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Pool.sortable_fields:
        raise exceptions.BadRequestException()
    
    experiment_lanes: dict[int, list[int]] = {}

    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    pools, _ = db.pools.find(
        offset=offset, experiment_id=experiment_id, sort_by=sort_by, descending=descending,
        limit=None
    )

    for lane in experiment.lanes:
        experiment_lanes[lane.number] = []
        
        for link in lane.pool_links:
            experiment_lanes[lane.number].append(link.pool_id)

    return make_response(
        render_template(
            "components/tables/experiment-pool.html",
            pools=pools, n_pages=1, active_page=0,
            sort_by=sort_by, sort_order=sort_order,
            experiment=experiment, experiment_lanes=experiment_lanes
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db)
def get_projects(current_user: models.User, experiment_id: int, page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Project.sortable_fields:
        raise exceptions.BadRequestException()

    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [ProjectStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
    
    projects, n_pages = db.projects.find(
        offset=offset, experiment_id=experiment_id, sort_by=sort_by, descending=descending, count_pages=True,
        status_in=status_in
    )

    return make_response(
        render_template(
            "components/tables/experiment-project.html",
            projects=projects, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            experiment=experiment, status_in=status_in,
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db)
def get_libraries(current_user: models.User, experiment_id: int, page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Library.sortable_fields:
        raise exceptions.BadRequestException()

    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    libraries, n_pages = db.libraries.find(
        offset=offset, experiment_id=experiment_id, sort_by=sort_by, descending=descending, count_pages=True
    )

    return make_response(
        render_template(
            "components/tables/experiment-library.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            experiment=experiment
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db)
def query_libraries(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (word := request.args.get("word")) is None:
        raise exceptions.BadRequestException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    libraries = db.libraries.query(experiment_id=experiment_id, name=word)

    return make_response(
        render_template(
            "components/tables/experiment-library.html",
            libraries=libraries, experiment=experiment
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db)
def get_comments(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()

    return make_response(
        render_template(
            "components/comment-list.html",
            comments=experiment.comments, experiment=experiment,
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db)
def get_files(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()

    return make_response(
        render_template(
            "components/file-list.html",
            files=experiment.media_files, experiment=experiment, delete="experiments_htmx.delete_file",
            delete_context={"experiment_id": experiment_id}
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db)
def get_pool_dilutions(current_user: models.User, experiment_id: int, page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    sort_by = request.args.get("sort_by", "pool_id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    dilutions, _ = db.pools.get_dilutions(offset=offset, experiment_id=experiment_id, sort_by=sort_by, descending=descending, limit=None)
    
    return make_response(
        render_template(
            "components/tables/experiment-pool-dilution.html",
            dilutions=dilutions, active_page=page,
            sort_by=sort_by, sort_order=sort_order, experiment=experiment,
        )
    )


@wrappers.htmx_route(experiments_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get_recent_experiments(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (sort_by := request.args.get("sort_by")) is not None:
        if sort_by not in ["name", "id", "timestamp_created_utc"]:
            raise exceptions.BadRequestException()
    else:
        sort_by = "name"

    experiments, _ = db.experiments.find(sort_by=sort_by, descending=True)

    return make_response(
        render_template("components/dashboard/experiments-list.html", experiments=experiments, sort_by=sort_by)
    )