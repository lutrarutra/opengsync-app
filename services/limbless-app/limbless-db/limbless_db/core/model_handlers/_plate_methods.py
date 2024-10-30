import math
from typing import Optional, TYPE_CHECKING

from sqlalchemy.sql.operators import and_

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from .. import exceptions


def create_plate(
    self: "DBHandler", name: str, num_cols: int, num_rows: int, owner_id: int,
) -> models.Plate:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (owner := self.get_user(owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")

    plate = models.Plate(
        name=name, num_cols=num_cols, num_rows=num_rows, owner=owner
    )

    self.session.add(plate)
    self.session.commit()

    if not persist_session:
        self.close_session()

    return plate


def get_plate(self: "DBHandler", plate_id: int) -> Optional[models.Plate]:
    if not (persist_session := self._session is not None):
        self.open_session()

    plate = self.session.get(models.Plate, plate_id)

    if not persist_session:
        self.close_session()

    return plate


def get_plates(
    self: "DBHandler",
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.Plate], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Plate)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

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

    if not persist_session:
        self.close_session()

    return plates, n_pages


def delete_plate(self: "DBHandler", plate_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()
    
    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    for sample_link in plate.sample_links:
        self.session.delete(sample_link)

    self.session.delete(plate)
    self.session.commit()

    if not persist_session:
        self.close_session()


def add_sample_to_plate(
    self: "DBHandler", plate_id: int, sample_id: int, well_idx: int
) -> models.Plate:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    if (_ := self.get_sample(sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    if self.session.query(models.links.SamplePlateLink).filter_by(plate_id=plate_id, well_idx=well_idx).first() is not None:
        raise exceptions.LinkAlreadyExists(f"Well {well_idx} is already occupied in plate with id {plate_id}")
    
    plate.sample_links.append(models.links.SamplePlateLink(
        plate_id=plate_id, well_idx=well_idx, sample_id=sample_id
    ))

    self.session.add(plate)
    self.session.commit()
    self.session.refresh(plate)

    if not persist_session:
        self.close_session()

    return plate


def add_library_to_plate(
    self: "DBHandler", plate_id: int, library_id: int, well_idx: int
) -> models.Plate:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    if (_ := self.get_library(library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if self.session.query(models.links.SamplePlateLink).filter_by(plate_id=plate_id, well_idx=well_idx).first() is not None:
        raise exceptions.LinkAlreadyExists(f"Well {well_idx} is already occupied in plate with id {plate_id}")
    
    plate.sample_links.append(models.links.SamplePlateLink(
        plate_id=plate_id, well_idx=well_idx, library_id=library_id
    ))

    self.session.add(plate)
    self.session.commit()
    self.session.refresh(plate)

    if not persist_session:
        self.close_session()

    return plate


def clear_plate(self: "DBHandler", plate_id: int) -> models.Plate:
    if not (persist_session := self._session is not None):
        self.open_session()
    
    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    for link in plate.sample_links:
        self.session.delete(link)
    
    self.session.add(plate)
    self.session.commit()
    self.session.refresh(plate)

    if not persist_session:
        self.close_session()

    return plate


def get_plate_sample(self: "DBHandler", plate_id: int, well_idx: int) -> Optional[models.Sample | models.Library]:
    if not (persist_session := self._session is not None):
        self.open_session()
    
    link: Optional[models.links.SamplePlateLink]
    link = self.session.query(models.links.SamplePlateLink).where(
        and_(
            models.links.SamplePlateLink.plate_id == plate_id,
            models.links.SamplePlateLink.well_idx == well_idx
        )
    ).first()

    if not persist_session:
        self.close_session()

    if link is None:
        return None
    
    return link.sample if link.sample is not None else link.library