import math
from typing import Optional

from ... import models, PAGE_LIMIT
from ..DBBlueprint import DBBlueprint
from .. import exceptions


class LaneBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, number: int, experiment_id: int
    ) -> models.Lane:
        if self.db.session.get(models.Experiment, experiment_id) is None:
            raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
        
        if self.db.session.query(models.Lane).where(
            models.Lane.number == number,
            models.Lane.experiment_id == experiment_id,
        ).first():
            raise exceptions.LinkAlreadyExists(f"Lane with number {number} already exists for experiment with id {experiment_id}")
        
        lane = models.Lane(
            number=number,
            experiment_id=experiment_id,
        )

        self.db.session.add(lane)
        return lane

    @DBBlueprint.transaction
    def get(self, lane_id: int) -> models.Lane | None:
        res = self.db.session.get(models.Lane, lane_id)
        return res

    @DBBlueprint.transaction
    def get_experiment_lane(self, experiment_id: int, lane_num: int) -> models.Lane | None:
        res = self.db.session.query(models.Lane).where(
            models.Lane.experiment_id == experiment_id,
            models.Lane.number == lane_num,
        ).first()
        return res

    @DBBlueprint.transaction
    def find(
        self, experiment_id: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        count_pages: bool = False
    ) -> tuple[list[models.Lane], int | None]:
        query = self.db.session.query(models.Lane)

        if experiment_id is not None:
            query = query.filter(models.Lane.experiment_id == experiment_id)

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

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
        return lanes, n_pages

    @DBBlueprint.transaction
    def update(self, lane: models.Lane):
        self.db.session.add(lane)

    @DBBlueprint.transaction
    def delete(self, lane_id: int, flush: bool = True):
        if (lane := self.db.session.get(models.Lane, lane_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Lane with id {lane_id} does not exist")
        
        for link in lane.pool_links:
            self.db.session.delete(link)
        
        lane.experiment.lanes.remove(lane)
        self.db.session.delete(lane)

        if flush:
            self.db.flush()