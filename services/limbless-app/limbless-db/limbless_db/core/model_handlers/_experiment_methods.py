import math
from datetime import datetime
from typing import Optional

import sqlalchemy as sa

from ... import models, PAGE_LIMIT
from .. import exceptions
from ...categories import FlowCellTypeEnum, SequencingWorkFlowTypeEnum, ExperimentStatus, LibraryStatus, SeqRequestStatus, PoolStatus


def create_experiment(
    self, name: str, flowcell_type: FlowCellTypeEnum, workflow_type: SequencingWorkFlowTypeEnum,
    sequencer_id: int, num_lanes: int, r1_cycles: int, i1_cycles: int, operator_id: int,
    r2_cycles: Optional[int] = None, i2_cycles: Optional[int] = None
) -> models.Experiment:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Sequencer, sequencer_id) is None:
        raise exceptions.ElementDoesNotExist(f"Sequencer with id {sequencer_id} does not exist")
    
    status = ExperimentStatus.DRAFT
    seq_run: models.SeqRun
    if (seq_run := self.get_seq_run(experiment_name=name)) is not None:
        status = seq_run.status

    experiment = models.Experiment(
        name=name,
        flowcell_type_id=flowcell_type.id,
        timestamp=datetime.now(),
        sequencer_id=sequencer_id,
        r1_cycles=r1_cycles,
        r2_cycles=r2_cycles,
        i1_cycles=i1_cycles,
        i2_cycles=i2_cycles,
        num_lanes=num_lanes,
        status_id=status.id,
        operator_id=operator_id,
        workflow_id=workflow_type.id
    )

    self._session.add(experiment)
    self._session.commit()
    self._session.refresh(experiment)

    if not persist_session:
        self.close_session()

    return experiment


def get_experiment(self, id: Optional[int] = None, name: Optional[str] = None) -> Optional[models.Experiment]:
    persist_session = self._session is not None
    if not self._session:
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
    sort_by: Optional[str] = None, descending: bool = False
) -> tuple[list[models.Experiment], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Experiment)

    if sort_by is not None:
        attr = getattr(models.Experiment, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

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
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Experiment).count()
    if not persist_session:
        self.close_session()
    return res


def delete_experiment(
    self, experiment_id: int,
    commit: bool = True
) -> None:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    experiment = self._session.get(models.Experiment, experiment_id)
    if not experiment:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

    self._session.delete(experiment)
    
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def update_experiment(self, experiment: models.Experiment) -> models.Experiment:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if experiment.num_lanes != experiment.flowcell_type.num_lanes:
        if experiment.num_lanes > experiment.flowcell_type.num_lanes:
            for lane in experiment.lanes:
                if lane.number > experiment.flowcell_type.num_lanes:
                    self._session.delete(lane)
        else:
            print(experiment.flowcell_type.num_lanes, experiment.num_lanes, len(experiment.lanes), flush=True)
            for lane_num in range(experiment.flowcell_type.num_lanes - experiment.num_lanes + 1, experiment.flowcell_type.num_lanes + 1):
                if lane_num in [lane.number for lane in experiment.lanes]:
                    raise ValueError(f"Lane {lane_num} already exists in experiment {experiment.id}")
                print("Creating lane", lane_num, flush=True)
                lane = models.Lane(number=lane_num, experiment_id=experiment.id)
                self._session.add(lane)

        experiment.num_lanes = experiment.flowcell_type.num_lanes

    self._session.add(experiment)
    self._session.commit()
    self._session.refresh(experiment)
    
    if experiment.workflow.combined_lanes:
        for lane in experiment.lanes:
            for pool in experiment.pools:
                if pool not in lane.pools:
                    lane.pools.append(pool)
                    pool.status_id = PoolStatus.LANED.id
                    self._session.add(lane)

    self._session.add(experiment)
    self._session.commit()
    self._session.refresh(experiment)

    if experiment.status_id == ExperimentStatus.FINISHED.id:
        seq_requests: list[models.SeqRequest] = []

        for lane in experiment.lanes:
            for pool in lane.pools:
                for library in pool.libraries:
                    library.status_id = LibraryStatus.SEQUENCED.id
                    self._session.add(library)
                    if library.seq_request not in seq_requests:
                        seq_requests.append(library.seq_request)

        self._session.commit()
        self._session.refresh(experiment)

        for seq_request in seq_requests:
            sequenced = True
            for library in seq_request.libraries:
                if library.status != LibraryStatus.SEQUENCED:
                    sequenced = False
                    break
            
            if sequenced:
                seq_request.status_id = SeqRequestStatus.DATA_PROCESSING.id
                self._session.add(seq_request)

    if not persist_session:
        self.close_session()

    return experiment


def query_experiments(self, word: str, limit: Optional[int] = PAGE_LIMIT) -> list[models.Experiment]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Experiment)

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
    persist_session = self._session is not None
    if not self._session:
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
    persist_session = self._session is not None
    if not self._session:
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
    persist_session = self._session is not None
    if not self._session:
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