import math
from typing import Optional, Callable

import sqlalchemy as sa
from sqlalchemy.orm import Query

from ... import models, PAGE_LIMIT
from .. import exceptions
from ...categories import ExperimentWorkFlowEnum, ExperimentStatusEnum, ExperimentWorkFlow
from ..DBBlueprint import DBBlueprint


class ExperimentBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query,
        status: Optional[ExperimentStatusEnum] = None,
        status_in: Optional[list[ExperimentStatusEnum]] = None,
        workflow_in: Optional[list[ExperimentWorkFlowEnum]] = None,
        custom_query: Callable[[Query], Query] | None = None,
    ) -> Query:
        if status is not None:
            query = query.where(models.Experiment.status_id == status.id)

        if status_in is not None:
            query = query.where(models.Experiment.status_id.in_([s.id for s in status_in]))

        if workflow_in is not None:
            query = query.where(models.Experiment.workflow_id.in_([w.id for w in workflow_in]))

        if custom_query is not None:
            query = custom_query(query)

        return query
    
    @DBBlueprint.transaction
    def create(
        self, name: str, workflow: ExperimentWorkFlowEnum, status: ExperimentStatusEnum,
        sequencer_id: int, r1_cycles: int, i1_cycles: int, operator_id: int,
        r2_cycles: int | None = None, i2_cycles: int | None = None, flush: bool = True
    ) -> models.Experiment:

        if self.db.session.get(models.Sequencer, sequencer_id) is None:
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

        self.db.session.add(experiment)

        if flush:
            self.db.flush()

        return experiment

    @DBBlueprint.transaction
    def get(self, id: int | None = None, name: Optional[str] = None) -> models.Experiment | None:

        if id is not None and name is None:
            experiment = self.db.session.get(models.Experiment, id)
        elif name is not None and id is None:
            experiment = self.db.session.query(models.Experiment).where(
                models.Experiment.name == name
            ).first()
        else:
            raise ValueError("Either 'id' or 'name' must be provided, not both.")

        return experiment

    @DBBlueprint.transaction
    def find(
        self,
        status: Optional[ExperimentStatusEnum] = None,
        status_in: Optional[list[ExperimentStatusEnum]] = None,
        workflow_in: Optional[list[ExperimentWorkFlowEnum]] = None,
        custom_query: Callable[[Query], Query] | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        count_pages: bool = False
    ) -> tuple[list[models.Experiment], int | None]:

        query = self.db.session.query(models.Experiment)
        query = ExperimentBP.where(
            query,
            status=status,
            status_in=status_in,
            workflow_in=workflow_in,
            custom_query=custom_query,
        )

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if sort_by is not None:
            attr = getattr(models.Experiment, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        experiments = query.all()

        return experiments, n_pages

    @DBBlueprint.transaction
    def delete(self, experiment_id: int, flush: bool = True):
        if (experiment := self.db.session.get(models.Experiment, experiment_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

        self.db.session.delete(experiment)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def update(self, experiment: models.Experiment):
        if (prev_workflow_id := self.db.session.query(models.Experiment.workflow_id).where(
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
                        self.db.lanes.delete(lane.id)

            elif prev_workflow.flow_cell_type.num_lanes < workflow.flow_cell_type.num_lanes:
                for lane_num in range(workflow.flow_cell_type.num_lanes - prev_workflow.flow_cell_type.num_lanes + 1, workflow.flow_cell_type.num_lanes + 1):
                    if lane_num in [lane.number for lane in experiment.lanes]:
                        raise ValueError(f"Lane {lane_num} already exists in experiment {experiment.id}")
                    lane = models.Lane(number=lane_num, experiment_id=experiment.id)
                    self.db.session.add(lane)
                
            if experiment.workflow.combined_lanes:
                lps = set([(link.lane_id, link.pool_id) for link in experiment.laned_pool_links])
                for lane in experiment.lanes:
                    for pool in experiment.pools:
                        if (lane.id, pool.id) not in lps:
                            lane = self.db.links.add_pool_to_lane(experiment_id=experiment.id, lane_num=lane.number, pool_id=pool.id)
            
        self.db.session.add(experiment)

    @DBBlueprint.transaction
    def query(
        self, word: str,
        workflow_in: Optional[list[ExperimentWorkFlowEnum]] = None,
        limit: int | None = PAGE_LIMIT
    ) -> list[models.Experiment]:

        query = self.db.session.query(models.Experiment)

        if workflow_in is not None:
            query = query.where(models.Experiment.workflow_id.in_([w.id for w in workflow_in]))

        query = query.order_by(
            sa.func.similarity(models.Experiment.name, word).desc()
        )

        if limit is not None:
            query = query.limit(limit)

        experiments = query.all()

        return experiments
    
    @DBBlueprint.transaction
    def __getitem__(self, key: int | str) -> models.Experiment:
        if isinstance(key, str):
            if (experiment := self.get(name=key)) is None:
                raise exceptions.ElementDoesNotExist(f"Experiment with name '{key}' does not exist")
        else:
            if (experiment := self.get(id=key)) is None:
                raise exceptions.ElementDoesNotExist(f"Experiment with id {key} does not exist")
        return experiment