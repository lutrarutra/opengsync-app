import math
from typing import Optional

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
    self, plate_id: int, sample_id: int, well: str
) -> models.Sample:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    plate: models.Plate
    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    sample: models.Sample
    if (sample := self.get_sample(sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    if plate.get_sample(well) is not None:
        raise exceptions.NotUniqueValue(f"Well {well} is already occupied in plate with id {plate_id}")
    
    sample.plate_id = plate.id
    sample.plate_well = well

    self._session.add(sample)
    self._session.commit()
    self._session.refresh(sample)

    if not persist_session:
        self.close_session()

    return sample


def add_library_to_plate(
    self, plate_id: int, library_id: int, well: str
) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    plate: models.Plate
    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    library: models.Library
    if (library := self.get_library(library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if plate.get_sample(well) is not None:
        raise exceptions.NotUniqueValue(f"Well {well} is already occupied in plate with id {plate_id}")
    
    library.plate_id = plate.id
    library.plate_well = well

    self._session.add(library)
    self._session.commit()
    self._session.refresh(library)

    if not persist_session:
        self.close_session()

    return library


def add_pool_to_plate(
    self, plate_id: int, pool_id: int, well: str
) -> models.Pool:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    plate: models.Plate
    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    pool: models.Pool
    if (pool := self.get_pool(pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
    
    if plate.get_sample(well) is not None:
        raise exceptions.NotUniqueValue(f"Well {well} is already occupied in plate with id {plate_id}")
    
    pool.plate_id = plate.id
    pool.plate_well = well

    self._session.add(pool)
    self._session.commit()
    self._session.refresh(pool)

    if not persist_session:
        self.close_session()

    return pool