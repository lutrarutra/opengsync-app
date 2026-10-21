import os

from fastapi import APIRouter, Depends
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import config, dependencies, responses, exceptions as exc

router = APIRouter(prefix="/experiments", tags=["experiments"], dependencies=[Depends(dependencies.require_insider)])


@router.get("/")
def experiments_page():
    return responses.html_response(template="experiments_page.html", title="Experiments")


@router.get("/{experiment_id}")
def experiment_page(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    path_list: list = Depends(dependencies.parse_from_page),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
        orm.selectinload(models.Experiment.lanes).selectinload(models.Lane.pool_links).selectinload(models.links.LanePoolLink.pool),
        orm.selectinload(models.Experiment.pools).selectinload(models.Pool.lane_links),
        orm.selectinload(models.Experiment.operator),
        orm.selectinload(models.Experiment.sequencer),
        orm.selectinload(models.Experiment.lane_pooling_tables),
        orm.selectinload(models.Experiment.sequencer_loading_checklists),
        orm.with_expression(models.Experiment._num_pools, models.Experiment.num_pools.expression),
        orm.with_expression(models.Experiment._num_libraries, models.Experiment.num_libraries.expression),
        orm.with_expression(models.Experiment._num_files, models.Experiment.num_files.expression),
        orm.with_expression(models.Experiment._num_comments, models.Experiment.num_comments.expression),
        orm.with_expression(models.Experiment._num_projects, models.Experiment.num_projects.expression),
        orm.with_expression(models.Experiment._num_data_paths, models.Experiment.num_data_paths.expression),
    ))

    checklist = experiment.get_checklist()
    steps = [
        checklist["pools_added"],
        checklist["lanes_assigned"],
        checklist["barcode_clashes_checked"],
        checklist["reads_assigned"],
        checklist["pool_qubits_measured"],
        checklist["pool_fragment_sizes_measured"],
        checklist["seq_requests_accepted"],
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
        template="experiment_page.html", experiment=experiment, title=experiment.name, path_list=path_list,
        pools=experiment.pools,
        selected_sequencer=experiment.sequencer.name,
        selected_user=experiment.operator,
        checklist_steps_completed=steps_completed,
        checklist_total_steps=len(steps),
        projects=session.scalars(Q.project.select(experiment_id=experiment.id).order_by(models.Project.id)).all(),
    )

@router.get("/{experiment_id}/lane-pooling-table/{file_id}")
def lane_pooling_table_page(
    experiment_id: int,
    file_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    """A lane pooling table of the experiment on its own page, e.g. to print a superseded one."""
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    file = session.get_one(Q.media_file.select(id=file_id, experiment_id=experiment.id))
    if file.type != C.MediaFileType.LANE_POOLING_TABLE:
        raise exc.NotFoundException(f"File {file.id} is not a lane pooling table.")

    latest = experiment.lane_pooling_table
    return responses.html_response(
        template="lane_pooling_table_page.html", experiment=experiment, file=file,
        title=f"{experiment.name} - Lane Pooling Table",
        latest=latest if latest is not None and latest.id != file.id else None,
        file_exists=os.path.isfile(os.path.join(config.settings.app_config.media_folder, file.path)),
        path_list=[
            ("Experiments", responses.url_for("experiments_page")),
            (experiment.name, responses.url_for("experiment_page", experiment_id=experiment.id)),
            (f"Lane Pooling Table {file.id}", ""),
        ],
    )
