import math
from typing import Optional

from ... import models, PAGE_LIMIT
from .. import exceptions


def create_lane(
    self, number: int, experiment_id: int
) -> models.Lane:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Experiment, experiment_id) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    
    if self._session.query(models.Lane).where(
        models.Lane.number == number,
        models.Lane.experiment_id == experiment_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Lane with number {number} already exists for experiment with id {experiment_id}")
    
    lane = models.Lane(
        number=number,
        experiment_id=experiment_id,
    )

    self._session.add(lane)
    self._session.commit()
    self._session.refresh(lane)

    if not persist_session:
        self.close_session()

    return lane


def get_lane(self, lane_id: int) -> Optional[models.Lane]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.Lane, lane_id)

    if not persist_session:
        self.close_session()
    return res


def get_experiment_lane(self, experiment_id: int, lane_num: int) -> Optional[models.Lane]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Lane).where(
        models.Lane.experiment_id == experiment_id,
        models.Lane.number == lane_num,
    ).first()

    if not persist_session:
        self.close_session()
    return res


def get_lanes(
    self, experiment_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
) -> tuple[list[models.Lane], int]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Lane)

    if experiment_id is not None:
        query = query.filter(models.Lane.experiment_id == experiment_id)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1
    
    query = query.order_by(models.Lane.number)

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    lanes = query.all()

    if not persist_session:
        self.close_session()
    
    return lanes, n_pages


def update_lane(
    self, lane: models.Lane,
) -> models.Lane:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    self._session.add(lane)
    self._session.commit()
    self._session.refresh(lane)

    if not persist_session:
        self.close_session()

    return lane