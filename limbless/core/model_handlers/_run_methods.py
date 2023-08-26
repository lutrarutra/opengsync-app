from typing import Optional, Union

from ... import models
from .. import exceptions
from ._link_methods import get_run_data

# FIXME: check that experiment exists
def create_run(
            self, lane: int,
            experiment_id: int,
            r1_cycles: int, i1_cycles: int, 
            r2_cycles: Optional[int] = None,
            i2_cycles: Optional[int] = None,
            commit: bool = True
        ) -> models.Run:
        persist_session = self._session is not None
        if not self._session:
            self.open_session()

        run = models.Run(
            lane=lane, r1_cycles=r1_cycles, i1_cycles=i1_cycles,
            r2_cycles=r2_cycles, i2_cycles=i2_cycles,
            experiment_id=experiment_id
        )

        self._session.add(run)
        if commit:
            self._session.commit()
            self._session.refresh(run)

        if not persist_session: self.close_session()
        return run

def get_run(self, run_id: int) -> models.Run:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    run = self._session.get(models.Run, run_id)
    if not persist_session: self.close_session()
    return run

def get_runs(self) -> list[models.Run]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    runs = self._session.query(models.Run).all()

    if not persist_session: self.close_session()
    return runs

def get_num_runs(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Run).count()
    if not persist_session: self.close_session()
    return res

def delete_run(
        self, run_id: int,
        commit: bool = True
    ) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    run = self._session.get(models.Run, run_id)
    if not run:
        raise exceptions.ElementDoesNotExist(f"Run with id {run_id} does not exist")
        
    self._session.delete(run)
    if commit: self._session.commit()

    if not persist_session: self.close_session()

def update_run(
        self, run_id: int,
        lane: Optional[int] = None,
        r1_cycles: Optional[int] = None,
        r2_cycles: Optional[int] = None, # FIXME: r2 can be deleted -> None
        i1_cycles: Optional[int] = None,
        i2_cycles: Optional[int] = None, # FIXME: i2 can be deleted -> None
        commit: bool = True
    ) -> models.Run:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    run = self._session.get(models.Run, run_id)
    if not run:
        raise exceptions.ElementDoesNotExist(f"Run with id {run_id} does not exist")

    if lane is not None: run.lane = lane
    if r1_cycles is not None: run.r1_cycles = r1_cycles
    if r2_cycles is not None: run.r2_cycles = r2_cycles
    if i1_cycles is not None: run.i1_cycles = i1_cycles
    if i2_cycles is not None: run.i2_cycles = i2_cycles

    if commit:
        self._session.commit()
        self._session.refresh(run)

    if not persist_session: self.close_session()
    return run

# TODO: testing
def get_run_num_samples(
        self, run_id: int
    ) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    run = self._session.get(models.Run, run_id)
    if not run:
        raise exceptions.ElementDoesNotExist(f"Run with id {run_id} does not exist")
    
    num_samples = len(get_run_data(self, run_id, unraveled=True))

    if not persist_session: self.close_session()
    return num_samples
    