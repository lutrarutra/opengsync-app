import math
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from .. import exceptions


def create_lane(
    self: "DBHandler", number: int, experiment_id: int
) -> models.Lane:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self.session.get(models.Experiment, experiment_id) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    
    if self.session.query(models.Lane).where(
        models.Lane.number == number,
        models.Lane.experiment_id == experiment_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Lane with number {number} already exists for experiment with id {experiment_id}")
    
    lane = models.Lane(
        number=number,
        experiment_id=experiment_id,
    )

    self.session.add(lane)
    self.session.commit()
    self.session.refresh(lane)

    if not persist_session:
        self.close_session()

    return lane


def get_lane(self: "DBHandler", lane_id: int) -> models.Lane | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.Lane, lane_id)

    if not persist_session:
        self.close_session()
    return res


def get_experiment_lane(self: "DBHandler", experiment_id: int, lane_num: int) -> models.Lane | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.query(models.Lane).where(
        models.Lane.experiment_id == experiment_id,
        models.Lane.number == lane_num,
    ).first()

    if not persist_session:
        self.close_session()
    return res


def get_lanes(
    self: "DBHandler", experiment_id: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
) -> tuple[list[models.Lane], int]:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Lane)

    if experiment_id is not None:
        query = query.filter(models.Lane.experiment_id == experiment_id)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if sort_by is not None:
        attr = getattr(models.Lane, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    query = query.order_by(models.Lane.number)

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    lanes = query.all()

    if not persist_session:
        self.close_session()
    
    return lanes, n_pages


def update_lane(self: "DBHandler", lane: models.Lane) -> models.Lane:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(lane)
    self.session.commit()
    self.session.refresh(lane)

    if not persist_session:
        self.close_session()

    return lane


def delete_lane(self: "DBHandler", lane_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (lane := self.session.get(models.Lane, lane_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Lane with id {lane_id} does not exist")
    
    for link in lane.pool_links:
        self.session.delete(link)
    
    lane.experiment.lanes.remove(lane)
    self.session.delete(lane)
    self.session.commit()

    if not persist_session:
        self.close_session()