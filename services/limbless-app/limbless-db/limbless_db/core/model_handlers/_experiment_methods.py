import math
from typing import Optional

import sqlalchemy as sa

from ... import models, PAGE_LIMIT
from .. import exceptions
from ...categories import ExperimentWorkFlowEnum, ExperimentStatusEnum, ExperimentWorkFlow


def create_experiment(
    self, name: str, workflow: ExperimentWorkFlowEnum, status: ExperimentStatusEnum,
    sequencer_id: int, r1_cycles: int, i1_cycles: int, operator_id: int,
    r2_cycles: Optional[int] = None, i2_cycles: Optional[int] = None
) -> models.Experiment:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self._session.get(models.Sequencer, sequencer_id) is None:
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
        num_lanes=workflow.flow_cell_type.num_lanes,
        operator_id=operator_id,
    )

    comment = models.Comment(
        text=f"Created experiment: {experiment.name} ({experiment.workflow.name}) [{experiment.id}]",
        author_id=operator_id,
    )
    self._session.add(comment)

    self._session.add(experiment)
    self._session.commit()
    self._session.refresh(experiment)

    for lane_num in range(1, workflow.flow_cell_type.num_lanes + 1):
        lane = models.Lane(number=lane_num, experiment_id=experiment.id)
        self._session.add(lane)

    self._session.commit()

    if not persist_session:
        self.close_session()

    return experiment


def get_experiment(self, id: Optional[int] = None, name: Optional[str] = None) -> Optional[models.Experiment]:
    if not (persist_session := self._session is not None):
        self.open_session()

    if id is not None and name is None:
        experiment = self._session.get(models.Experiment, id)
    elif name is not None and id is None:
        experiment = self._session.query(models.Experiment).where(
            models.Experiment.name == name
        ).first()
    else:
        raise ValueError("Either 'id' or 'name' must be provided, not both.")

    if not persist_session:
        self.close_session()

    return experiment


def get_experiments(
    self, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    status: Optional[ExperimentStatusEnum] = None,
    status_in: Optional[list[ExperimentStatusEnum]] = None,
    workflow_in: Optional[list[ExperimentWorkFlowEnum]] = None,
    sort_by: Optional[str] = None, descending: bool = False
) -> tuple[list[models.Experiment], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.Experiment)

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

    n_pages = math.ceil(query.count() / limit)

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    experiments = query.all()

    if not persist_session:
        self.close_session()

    return experiments, n_pages


def get_num_experiments(self) -> int:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self._session.query(models.Experiment).count()
    if not persist_session:
        self.close_session()
    return res


def delete_experiment(self, experiment_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()
    
    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

    self._session.delete(experiment)
    self._session.commit()

    if not persist_session:
        self.close_session()


def update_experiment(self, experiment: models.Experiment) -> models.Experiment:
    if not (persist_session := self._session is not None):
        self.open_session()

    prev_workflow = ExperimentWorkFlow.get(self._session.query(models.Experiment.workflow_id).where(
        models.Experiment.id == experiment.id,
    ).first()[0])

    self._session.add(experiment)
    self._session.commit()
    self._session.refresh(experiment)

    if experiment.workflow != prev_workflow:
        workflow = experiment.workflow
        experiment.workflow = workflow
        experiment.num_lanes = workflow.flow_cell_type.num_lanes

        if prev_workflow.flow_cell_type.num_lanes > workflow.flow_cell_type.num_lanes:
            lanes = experiment.lanes.copy()
            for lane in lanes:
                if lane.number > experiment.flowcell_type.num_lanes:
                    for pool in lane.pools:
                        lane.pools.remove(pool)
                    experiment.lanes.remove(lane)

        elif prev_workflow.flow_cell_type.num_lanes < workflow.flow_cell_type.num_lanes:
            for lane_num in range(workflow.flow_cell_type.num_lanes - prev_workflow.flow_cell_type.num_lanes + 1, workflow.flow_cell_type.num_lanes + 1):
                if lane_num in [lane.number for lane in experiment.lanes]:
                    raise ValueError(f"Lane {lane_num} already exists in experiment {experiment.id}")
                print("Creating lane", lane_num, flush=True)
                lane = models.Lane(number=lane_num, experiment_id=experiment.id)
                self._session.add(lane)

        self._session.add(experiment)
        self._session.commit()
        self._session.refresh(experiment)
        if experiment.workflow.combined_lanes:
            for lane in experiment.lanes:
                for pool in experiment.pools:
                    if pool not in lane.pools:
                        lane.pools.append(pool)

            self._session.add(experiment)
            self._session.commit()
            self._session.refresh(experiment)

    if not persist_session:
        self.close_session()

    return experiment


def query_experiments(
    self, word: str,
    workflow_in: Optional[list[ExperimentWorkFlowEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT
) -> list[models.Experiment]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.Experiment)

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


def add_file_to_experiment(
    self, experiment_id: int, file_id: int,
    commit: bool = True
) -> models.ExperimentFileLink:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id '{experiment_id}', not found.")

    if (_ := self._session.get(models.File, file_id)) is None:
        raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
    
    file_link = models.ExperimentFileLink(
        experiment_id=experiment_id,
        file_id=file_id
    )
    self._session.add(file_link)

    if commit:
        self._session.commit()
        self._session.refresh(file_link)

    if not persist_session:
        self.close_session()

    return file_link


def remove_comment_from_experiment(self, experiment_id: int, comment_id: int, commit: bool = True) -> None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id '{experiment_id}', not found.")

    if (comment := self._session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id '{comment_id}', not found.")
    
    experiment.comments.remove(comment)
    self._session.add(experiment)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()
    return None


def remove_file_from_experiment(self, experiment_id: int, file_id: int, commit: bool = True) -> None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id '{experiment_id}', not found.")

    if (file := self._session.get(models.File, file_id)) is None:
        raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
    
    experiment.files.remove(file)

    comments = self._session.query(models.Comment).where(
        models.Comment.file_id == file_id
    ).all()

    for comment in comments:
        self.remove_comment_from_experiment(experiment_id, comment.id, commit=False)

    self._session.add(experiment)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()
    return None