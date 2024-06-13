import math
from typing import Optional

from ... import models, PAGE_LIMIT
from .. import exceptions


def create_plate(
    self, name: str, num_cols: int, num_rows: int, owner_id: int,
    pool_id: Optional[int] = None
) -> models.Plate:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (owner := self.get_user(owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")
    
    if pool_id is not None:
        if (pool := self.get_pool(pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
    else:
        pool = None

    plate = models.Plate(
        name=name, num_cols=num_cols, num_rows=num_rows, owner=owner, pool=pool
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
    self, library_id: Optional[int] = None, pool_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.Plate], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Plate)

    if library_id is not None:
        query = query.join(
            models.LibraryPlateLink,
            models.LibraryPlateLink.plate_id == models.Plate.id
        ).where(
            models.LibraryPlateLink.library_id == library_id
        )

    if pool_id is not None:
        query = query.where(models.Plate.pool_id == pool_id)

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

    if plate.pool is not None:
        plate.pool.plate_id = None
        self._session.add(plate.pool)

    self._session.delete(plate)
    self._session.commit()

    if not persist_session:
        self.close_session()


def add_library_to_plate(
    self, plate_id: int, library_id: int, well: str
) -> models.LibraryPlateLink:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")
    
    if (library := self.get_library(library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if self._session.query(models.LibraryPlateLink).where(
        models.LibraryPlateLink.plate_id == plate_id,
        models.LibraryPlateLink.library_id == library.id
    ).first() is not None:
        raise exceptions.LinkAlreadyExists(f"Library with id {library_id} is already in plate with id {plate_id}")
    if self._session.query(models.LibraryPlateLink).where(
        models.LibraryPlateLink.plate_id == plate_id,
        models.LibraryPlateLink.well == well
    ).first():
        raise exceptions.NotUniqueValue(f"Well {well} is already occupied in plate with id {plate_id}")
    
    library_plate_link = models.LibraryPlateLink(
        plate_id=plate_id, library_id=library_id, well=well
    )

    self._session.add(library_plate_link)
    self._session.commit()

    if not persist_session:
        self.close_session()

    return library_plate_link


def get_plate_libraries(self, plate_id: int) -> list[models.LibraryPlateLink]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (plate := self.get_plate(plate_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Plate with id {plate_id} does not exist")

    links = plate.library_links

    if not persist_session:
        self.close_session()

    return links