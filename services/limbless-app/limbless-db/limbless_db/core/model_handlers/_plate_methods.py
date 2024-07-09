import math
from typing import Optional

from sqlalchemy.sql.operators import and_

from ... import models, PAGE_LIMIT
from .. import exceptions


def create_plate(
    self, name: str, num_cols: int, num_rows: int, owner_id: int,
) -> models.Plate:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (owner := self.get_user(owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")

    plate = models.Plate(
        name=name, num_cols=num_cols, num_rows=num_rows, owner=owner
    )

    self._session.add(plate)
    self._session.commit()

    if not persist_session:
        self.close_session()

    return plate


def get_plate(self, plate_id: int) -> Optional[models.Plate]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    plate = self._session.get(models.Plate, plate_id)

    if not persist_session:
        self.close_session()

    return plate


def get_plates(
    self,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.Plate], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Plate)

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


def delete_plate(self, plate_id: int):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
    
    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    for library_link in plate.library_links:
        self._session.delete(library_link)

    self._session.delete(plate)
    self._session.commit()

    if not persist_session:
        self.close_session()


def add_sample_to_plate(
    self, plate_id: int, sample_id: int, well_idx: int
) -> models.Plate:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    plate: models.Plate
    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    if (_ := self.get_sample(sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    if self._session.query(models.SamplePlateLink).filter_by(plate_id=plate_id, well_idx=well_idx).first() is not None:
        raise exceptions.LinkAlreadyExists(f"Well {well_idx} is already occupied in plate with id {plate_id}")
    
    plate.sample_links.append(models.SamplePlateLink(
        plate_id=plate_id, well_idx=well_idx, sample_id=sample_id
    ))

    self._session.add(plate)
    self._session.commit()
    self._session.refresh(plate)

    if not persist_session:
        self.close_session()

    return plate


def add_library_to_plate(
    self, plate_id: int, library_id: int, well_idx: int
) -> models.Plate:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    plate: models.Plate
    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    if (_ := self.get_library(library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if self._session.query(models.SamplePlateLink).filter_by(plate_id=plate_id, well_idx=well_idx).first() is not None:
        raise exceptions.LinkAlreadyExists(f"Well {well_idx} is already occupied in plate with id {plate_id}")
    
    plate.sample_links.append(models.SamplePlateLink(
        plate_id=plate_id, well_idx=well_idx, library_id=library_id
    ))

    self._session.add(plate)
    self._session.commit()
    self._session.refresh(plate)

    if not persist_session:
        self.close_session()

    return plate


def clear_plate(self, plate_id: int) -> models.Plate:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
    
    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    for link in plate.sample_links:
        print(link, flush=True)
        self._session.delete(link)
    
    self._session.add(plate)
    self._session.commit()
    self._session.refresh(plate)

    if not persist_session:
        self.close_session()

    return plate


def get_plate_sample(self, plate_id: int, well_idx: int) -> Optional[models.Sample | models.Library]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
    
    link: Optional[models.SamplePlateLink]
    link = self._session.query(models.SamplePlateLink).where(
        and_(
            models.SamplePlateLink.plate_id == plate_id,
            models.SamplePlateLink.well_idx == well_idx
        )
    ).first()

    if not persist_session:
        self.close_session()

    if link is None:
        return None
    
    return link.sample if link.sample is not None else link.library