from typing import Optional

from ... import models
from .. import exceptions


def create_experiment(
    self, flowcell: str, sequencer_id: int, num_lanes: int,
    r1_cycles: int, i1_cycles: int,
    r2_cycles: Optional[int] = None, i2_cycles: Optional[int] = None,
    commit: bool = True
) -> models.Experiment:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Sequencer, sequencer_id) is None:
        raise exceptions.ElementDoesNotExist(f"Sequencer with id {sequencer_id} does not exist")

    experiment = models.Experiment(
        flowcell=flowcell, timestamp=None,
        sequencer_id=sequencer_id,
        r1_cycles=r1_cycles,
        r2_cycles=r2_cycles,
        i1_cycles=i1_cycles,
        i2_cycles=i2_cycles,
        num_lanes=num_lanes
    )

    self._session.add(experiment)
    if commit:
        self._session.commit()
        self._session.refresh(experiment)

    if not persist_session:
        self.close_session()

    return experiment


def get_experiment(self, experiment_id: int) -> models.Experiment:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.Experiment, experiment_id)
    if not persist_session:
        self.close_session()
    return res


def get_experiment_by_name(self, experiment_name) -> models.Experiment:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Experiment).where(
        models.Experiment.name == experiment_name
    ).first()

    if not persist_session:
        self.close_session()
    return res


def get_experiments(
    self, limit: Optional[int] = 20, offset: Optional[int] = None,
    sort_by: Optional[str] = None, reversed: bool = False
) -> list[models.Experiment]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Experiment)

    if sort_by is not None:
        attr = getattr(models.Experiment, sort_by)
        if reversed:
            attr = attr.desc()
        query = query.order_by(attr)

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    experiments = query.all()

    if not persist_session:
        self.close_session()

    return experiments


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


def update_experiment(
    self, experiment_id: int,
    name: Optional[str] = None,
    flowcell: Optional[str] = None,
    r1_cycles: Optional[int] = None,
    r2_cycles: Optional[int] = None,
    i1_cycles: Optional[int] = None,
    i2_cycles: Optional[int] = None,
    num_lanes: Optional[int] = None,
    sequencer_id: Optional[int] = None,
    commit: bool = True
) -> models.Experiment:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    experiment = self._session.get(models.Experiment, experiment_id)
    if not experiment:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

    if name is not None:
        if self._session.query(models.Experiment).where(
            models.Experiment.name == name
        ).first() is not None:
            raise exceptions.NotUniqueValue(f"Experiment with name {name} already exists")

    if name is not None:
        experiment.name = name
    if flowcell is not None:
        experiment.flowcell = flowcell
    if r1_cycles is not None:
        experiment.r1_cycles = r1_cycles
    if i1_cycles is not None:
        experiment.i1_cycles = i1_cycles
    if num_lanes is not None:
        experiment.num_lanes = num_lanes
        
    experiment.r2_cycles = r2_cycles
    experiment.i2_cycles = i2_cycles
    experiment.sequencer_id = sequencer_id

    if commit:
        self._session.commit()
        self._session.refresh(experiment)

    if not persist_session:
        self.close_session()
    return experiment