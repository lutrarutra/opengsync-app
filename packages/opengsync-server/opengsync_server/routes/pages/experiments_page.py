from flask import Blueprint, render_template, url_for, request

from sqlalchemy import orm

from opengsync_db import models

from ... import db, logger
from ...core import wrappers, exceptions
experiments_page_bp = Blueprint("experiments_page", __name__)


@wrappers.page_route(experiments_page_bp, db=db, cache_timeout_seconds=360)
def experiments(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    return render_template("experiments_page.html")


@wrappers.page_route(experiments_page_bp, "experiments", db=db, cache_timeout_seconds=360)
def experiment(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    if (experiment := db.experiments.get(
        experiment_id, options=[
            orm.selectinload(models.Experiment.pools),
            orm.selectinload(models.Experiment.lanes).selectinload(models.Lane.pool_links),
            orm.selectinload(models.Experiment.media_files),
        ])  # type: ignore
    ) is None:
        raise exceptions.NotFoundException()

    experiment_lanes: dict[int, list[int]] = {}

    for lane in experiment.lanes:
        experiment_lanes[lane.number] = []

        for link in lane.pool_links:
            experiment_lanes[lane.number].append(link.pool_id)

    path_list = [
        ("Experiments", url_for("experiments_page.experiments")),
        (f"Experiment {experiment_id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "seq_run":
            path_list = [
                ("Runs", url_for("seq_runs_page.seq_runs")),
                (f"Run {id}", url_for("seq_runs_page.seq_run", seq_run_id=id)),
                (f"Experiment {experiment_id}", ""),
            ]
        elif page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries")),
                (f"Library {id}", url_for("libraries_page.library", library_id=id)),
                (f"Experiment {experiment_id}", ""),
            ]

    checklist = experiment.get_checklist()
    steps = [
        checklist["pools_added"],
        checklist["lanes_assigned"],
        checklist["reads_assigned"],
        checklist["pool_qubits_measured"],
        checklist["pool_fragment_sizes_measured"],
        checklist["lane_qubit_measured"],
        checklist["lane_fragment_size_measured"],
        checklist["laning_completed"],
        checklist["flowcell_loaded"],
    ]
    steps_completed = sum(1 for item in steps if item)

    return render_template(
        "experiment_page.html",
        experiment=experiment,
        path_list=path_list,
        pools=experiment.pools,
        experiment_lanes=experiment_lanes,
        selected_sequencer=experiment.sequencer.name,
        selected_user=experiment.operator,
        checklist_steps_completed=steps_completed,
        checklist_total_steps=len(steps)
    )
