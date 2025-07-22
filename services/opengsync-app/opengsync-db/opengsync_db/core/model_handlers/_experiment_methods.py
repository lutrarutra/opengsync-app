import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from .. import exceptions
from ...categories import ExperimentWorkFlowEnum, ExperimentStatusEnum, ExperimentWorkFlow


def create_experiment(
    self: "DBHandler", name: str, workflow: ExperimentWorkFlowEnum, status: ExperimentStatusEnum,
    sequencer_id: int, r1_cycles: int, i1_cycles: int, operator_id: int,
    r2_cycles: Optional[int] = None, i2_cycles: Optional[int] = None, flush: bool = True
) -> models.Experiment:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self.session.get(models.Sequencer, sequencer_id) is None:
        raise exceptions.ElementDoesNotExist(f"Sequencer with id {sequencer_id} does not exist")

    experiment = models.Experiment(
        name=name.strip(),
        sequencer_id=sequencer_id,
        workflow_id=workflow.id,
        r1_cycles=r1_cycles,
        r2_cycles=r2_cycles,
        i1_cycles=i1_cycles,
        i2_cycles=i2_cycles,
        status_id=status.id,
        operator_id=operator_id,
    )

    for lane_num in range(1, workflow.flow_cell_type.num_lanes + 1):
        lane = models.Lane(number=lane_num, experiment_id=experiment.id)
        experiment.lanes.append(lane)

    self.session.add(experiment)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()

    return experiment


def get_experiment(self: "DBHandler", id: Optional[int] = None, name: Optional[str] = None) -> models.Experiment | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if id is not None and name is None:
        experiment = self.session.get(models.Experiment, id)
    elif name is not None and id is None:
        experiment = self.session.query(models.Experiment).where(
            models.Experiment.name == name
        ).first()
    else:
        raise ValueError("Either 'id' or 'name' must be provided, not both.")

    if not persist_session:
        self.close_session()

    return experiment


def get_experiments(
    self: "DBHandler", limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    status: Optional[ExperimentStatusEnum] = None,
    status_in: Optional[list[ExperimentStatusEnum]] = None,
    workflow_in: Optional[list[ExperimentWorkFlowEnum]] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    count_pages: bool = False
) -> tuple[list[models.Experiment], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Experiment)

    if sort_by is not None:
        attr = getattr(models.Experiment, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    if status is not None:
        query = query.where(models.Experiment.status_id == status.id)

    if status_in is not None:
        query = query.where(models.Experiment.status_id.in_([s.id for s in status_in]))

    if workflow_in is not None:
        query = query.where(models.Experiment.workflow_id.in_([w.id for w in workflow_in]))

    n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    experiments = query.all()

    if not persist_session:
        self.close_session()

    return experiments, n_pages


def get_num_experiments(self: "DBHandler") -> int:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.query(models.Experiment).count()
    if not persist_session:
        self.close_session()
    return res


def delete_experiment(self: "DBHandler", experiment_id: int, flush: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()
    
    if (experiment := self.session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

    self.session.delete(experiment)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()


def update_experiment(self: "DBHandler", experiment: models.Experiment) -> models.Experiment:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (prev_workflow_id := self.session.query(models.Experiment.workflow_id).where(
        models.Experiment.id == experiment.id,
    ).first()) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment.id} does not exist")
    
    prev_workflow = ExperimentWorkFlow.get(prev_workflow_id[0])

    if experiment.workflow != prev_workflow:
        workflow = experiment.workflow
        experiment.workflow = workflow

        if prev_workflow.flow_cell_type.num_lanes > workflow.flow_cell_type.num_lanes:
            lanes = experiment.lanes.copy()
            for lane in lanes:
                if lane.number > experiment.flowcell_type.num_lanes:
                    self.delete_lane(lane.id)

        elif prev_workflow.flow_cell_type.num_lanes < workflow.flow_cell_type.num_lanes:
            for lane_num in range(workflow.flow_cell_type.num_lanes - prev_workflow.flow_cell_type.num_lanes + 1, workflow.flow_cell_type.num_lanes + 1):
                if lane_num in [lane.number for lane in experiment.lanes]:
                    raise ValueError(f"Lane {lane_num} already exists in experiment {experiment.id}")
                lane = models.Lane(number=lane_num, experiment_id=experiment.id)
                self.session.add(lane)
            
        if experiment.workflow.combined_lanes:
            lps = set([(link.lane_id, link.pool_id) for link in experiment.laned_pool_links])
            for lane in experiment.lanes:
                for pool in experiment.pools:
                    if (lane.id, pool.id) not in lps:
                        lane = self.add_pool_to_lane(experiment_id=experiment.id, lane_num=lane.number, pool_id=pool.id)
        
    self.session.add(experiment)

    if not persist_session:
        self.close_session()

    return experiment


def query_experiments(
    self: "DBHandler", word: str,
    workflow_in: Optional[list[ExperimentWorkFlowEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT
) -> list[models.Experiment]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Experiment)

    if workflow_in is not None:
        query = query.where(models.Experiment.workflow_id.in_([w.id for w in workflow_in]))

    query = query.order_by(
        sa.func.similarity(models.Experiment.name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    experiments = query.all()

    if not persist_session:
        self.close_session()

    return experiments