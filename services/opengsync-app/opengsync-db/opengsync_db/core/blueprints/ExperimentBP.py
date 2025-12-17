import math
from typing import Optional, Callable, Iterable

import sqlalchemy as sa
from sqlalchemy.orm import Query, interfaces
from sqlalchemy.sql.base import ExecutableOption

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
        project_id: Optional[int] = None,
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

        if project_id is not None:
            query = query.where(
                sa.exists().where(
                    (models.Project.id == project_id) &
                    (models.Sample.project_id == models.Project.id) &
                    (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
                    (models.Library.id == models.links.SampleLibraryLink.library_id) &
                    (models.Library.experiment_id == models.Experiment.id)
                )
            )

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
    def get(self, key: int | str, options: ExecutableOption | None = None) -> models.Experiment | None:
        if isinstance(key, int):
            if options is not None:
                experiment = self.db.session.query(models.Experiment).options(options).filter(
                    models.Experiment.id == key
                ).first()
            else:        
                experiment = self.db.session.get(models.Experiment, key)
        elif isinstance(key, str):
            query = self.db.session.query(models.Experiment)
            if options is not None:
                query = query.options(options)
            experiment = query.filter(
                models.Experiment.name == key
            ).first()
        else:
            raise ValueError("Either 'id' or 'name' must be provided, not both.")

        return experiment

    @DBBlueprint.transaction
    def find(
        self,
        project_id: Optional[int] = None,
        status: Optional[ExperimentStatusEnum] = None,
        status_in: Optional[list[ExperimentStatusEnum]] = None,
        workflow_in: Optional[list[ExperimentWorkFlowEnum]] = None,
        operator: str | None = None,
        id: int | None = None,
        name: str | None = None,
        custom_query: Callable[[Query], Query] | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        page: int | None = None,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.Experiment], int | None]:

        query = self.db.session.query(models.Experiment)
        query = ExperimentBP.where(
            query,
            project_id=project_id,
            status=status,
            status_in=status_in,
            workflow_in=workflow_in,
            custom_query=custom_query,
        )
        if options is not None:
            query = query.options(options)

        if sort_by is not None:
            attr = getattr(models.Experiment, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        if name is not None:
            query = query.order_by(
                sa.nulls_last(sa.func.similarity(models.Experiment.name, name).desc())
            )
        elif id is not None:
            query = query.where(models.Experiment.id == id)
        elif operator is not None:
            query = query.join(
                models.User,
                models.Experiment.operator_id == models.User.id
            ).order_by(
                sa.nulls_last(sa.func.similarity(models.User.first_name + " " + models.User.last_name, operator).desc())
            )

        if page is not None:
            if limit is None:
                raise ValueError("Limit must be provided when page is provided")
            
            count = query.count()
            n_pages = math.ceil(count / limit)
            query = query.offset(min(page, max(0, n_pages - 1)) * limit)
        else:
            n_pages = None

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
            if len(experiment.lanes) > experiment.num_lanes:
                lanes = experiment.lanes.copy()
                for lane in lanes:
                    if lane.number > experiment.num_lanes:
                        experiment.lanes.remove(lane)

            elif len(experiment.lanes) < experiment.num_lanes:
                for lane_num in range(1, experiment.num_lanes + 1):
                    if lane_num in [lane.number for lane in experiment.lanes]:
                        continue
                    experiment.lanes.append(models.Lane(number=lane_num))
                
            self.db.flush()
            if experiment.workflow.combined_lanes:
                lps = set([(link.lane_id, link.pool_id) for link in experiment.laned_pool_links])
                for lane in experiment.lanes:
                    for pool in experiment.pools:
                        if (lane.id, pool.id) not in lps:
                            lane = self.db.links.add_pool_to_lane(experiment_id=experiment.id, lane_num=lane.number, pool_id=pool.id)
        
        if len(experiment.lanes) != experiment.num_lanes:
            raise ValueError(f"Experiment {experiment.id} has {len(experiment.lanes)} lanes, but workflow {experiment.workflow.name} requires {experiment.workflow.flow_cell_type.num_lanes} lanes.")
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
        if (experiment := self.get(key)) is None:
            raise exceptions.ElementDoesNotExist(f"Experiment with name '{key}' does not exist")
        return experiment