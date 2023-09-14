from typing import Optional, Union

from ... import models
from .. import exceptions


def create_experiment(
    self, name: str, flowcell: str, commit: bool = True
) -> list[models.Sample]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.Experiment).where(
        models.Experiment.name == name
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"Experiment with name {name} already exists")

    experiment = models.Experiment(
        name=name, flowcell=flowcell
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

# TODO: testing


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


def get_experiments(self) -> list[models.Experiment]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    experiments = self._session.query(models.Experiment).all()
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

    self._session.add(experiment)
    if commit:
        self._session.commit()
        self._session.refresh(experiment)

    if not persist_session:
        self.close_session()
    return experiment