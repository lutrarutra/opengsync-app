from fastapi import APIRouter, Depends
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...core import dependencies, responses

router = APIRouter(prefix="/experiments", tags=["experiments"], dependencies=[Depends(dependencies.require_insider)])


@router.get("/")
def experiments_page():
    return responses.html_response("experiments_page.html", title="Experiments")


@router.get("/{experiment_id}")
def experiment_page(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    path_list: list = Depends(dependencies.parse_from_page),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
        orm.selectinload(models.Experiment.lanes).selectinload(models.Lane.pool_links),
    ))
    experiment_lanes: dict[int, list[int]] = {}

    for lane in experiment.lanes:
        experiment_lanes[lane.number] = []

        for link in lane.pool_links:
            experiment_lanes[lane.number].append(link.pool_id)

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
        checklist["num_cycles_set"]
    ]
    if experiment.workflow.load_sequencer_workflow_checklist is not None:
        steps.append(checklist["loading_checklist_generated"])
    steps_completed = sum(1 for item in steps if item)
    return responses.html_response(
        "experiment_page.html", experiment=experiment, title=experiment.name, path_list=path_list,
        pools=experiment.pools,
        experiment_lanes=experiment_lanes,
        selected_sequencer=experiment.sequencer.name,
        selected_user=experiment.operator,
        checklist_steps_completed=steps_completed,
        checklist_total_steps=len(steps),
    )