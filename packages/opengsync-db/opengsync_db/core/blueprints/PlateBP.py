import math
from typing import Optional

from sqlalchemy.sql.operators import and_

from ... import models, PAGE_LIMIT
from ..DBBlueprint import DBBlueprint
from .. import exceptions


class PlateBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, name: str, num_cols: int, num_rows: int, owner_id: int, flush: bool = True
    ) -> models.Plate:
        if (owner := self.db.users.get(owner_id)) is None:
            raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")

        plate = models.Plate(name=name, num_cols=num_cols, num_rows=num_rows, owner=owner)
        self.db.session.add(plate)

        if flush:
            self.db.flush()

        return plate

    @DBBlueprint.transaction
    def get(self, plate_id: int) -> models.Plate | None:
        plate = self.db.session.get(models.Plate, plate_id)
        return plate

    @DBBlueprint.transaction
    def find(
        self,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: str | None = None, descending: bool = False,
        count_pages: bool = False
    ) -> tuple[list[models.Plate], int | None]:
        query = self.db.session.query(models.Plate)
        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if sort_by is not None:
            attr = getattr(models.Library, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)
        
        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        plates = query.all()
        return plates, n_pages

    @DBBlueprint.transaction
    def delete(self, plate_id: int, flush: bool = True):
        if (plate := self.get(plate_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
        
        for sample_link in plate.sample_links:
            self.db.session.delete(sample_link)

        self.db.session.delete(plate)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def add_sample(
        self, plate_id: int, sample_id: int, well_idx: int
    ) -> models.Plate:
        if (plate := self.get(plate_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
        
        if self.db.session.query(models.links.SamplePlateLink).filter_by(plate_id=plate_id, well_idx=well_idx).first() is not None:
            raise exceptions.LinkAlreadyExists(f"Well {well_idx} is already occupied in plate with id {plate_id}")
        
        plate.sample_links.append(models.links.SamplePlateLink(
            plate_id=plate_id, well_idx=well_idx, sample_id=sample_id
        ))

        self.db.session.add(plate)
        return plate

    @DBBlueprint.transaction
    def add_library(
        self, plate_id: int, library_id: int, well_idx: int
    ) -> models.Plate:
        if (plate := self.get(plate_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
        
        if self.db.session.query(models.links.SamplePlateLink).filter_by(plate_id=plate_id, well_idx=well_idx).first() is not None:
            raise exceptions.LinkAlreadyExists(f"Well {well_idx} is already occupied in plate with id {plate_id}")
        
        plate.sample_links.append(models.links.SamplePlateLink(
            plate_id=plate_id, well_idx=well_idx, library_id=library_id
        ))

        self.db.session.add(plate)
        return plate

    @DBBlueprint.transaction
    def clear(self, plate_id: int) -> models.Plate:
        if (plate := self.get(plate_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
        
        for link in plate.sample_links:
            self.db.session.delete(link)
        
        self.db.session.add(plate)
        return plate

    @DBBlueprint.transaction
    def get_sample(self, plate_id: int, well_idx: int) -> models.Sample | models.Library | None:
        link: Optional[models.links.SamplePlateLink]
        link = self.db.session.query(models.links.SamplePlateLink).where(
            and_(
                models.links.SamplePlateLink.plate_id == plate_id,
                models.links.SamplePlateLink.well_idx == well_idx
            )
        ).first()
        if link is None:
            return None
        
        return link.sample if link.sample is not None else link.library