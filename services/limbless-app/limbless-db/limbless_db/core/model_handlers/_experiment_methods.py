import math
from datetime import datetime
from typing import Optional

from ... import models, PAGE_LIMIT
from .. import exceptions
from ...categories import FlowCellTypeEnum, ExperimentStatus, LibraryStatus, SeqRequestStatus


def create_experiment(
    self, name: str, flowcell_type: FlowCellTypeEnum, sequencer_id: int,
    num_lanes: int, r1_cycles: int, i1_cycles: int, operator_id: int,
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
    
    if experiment is not None:
        if (seq_run := self._session.query(models.SeqRun).where(models.SeqRun.experiment_name == experiment.name).first()) is not None:
            experiment._seq_run_ = seq_run

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