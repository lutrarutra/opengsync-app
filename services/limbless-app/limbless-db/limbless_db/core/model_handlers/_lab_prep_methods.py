import math
from typing import Optional

from ... import models, PAGE_LIMIT
from ...categories import LabProtocolEnum, LibraryStatus
from .. import exceptions


def create_lab_prep(
    self, name: str, creator_id: int, protocol: LabProtocolEnum,
) -> models.LabPrep:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (creator := self._session.get(models.User, creator_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{creator_id}', not found.")

    lab_prep = models.LabPrep(
        name=name.strip(),
        creator_id=creator.id,
        protocol_id=protocol.id,
    )

    self._session.add(lab_prep)
    self._session.commit()
    self._session.refresh(lab_prep)

    if not persist_session:
        self.close_session()
    return lab_prep


def get_lab_prep(
    self, lab_prep_id: int
) -> Optional[models.LabPrep]:
    if not (persist_session := self._session is not None):
        self.open_session()

    lab_prep = self._session.get(models.LabPrep, lab_prep_id)

    if not persist_session:
        self.close_session()

    return lab_prep


def get_lab_preps(
    self, procotol: Optional[LabProtocolEnum] = None,
    protocol_in: Optional[list[LabProtocolEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.LabPrep], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.LabPrep)

    if procotol is not None:
        query = query.filter(models.LabPrep.protocol_id == procotol.id)
    elif protocol_in is not None:
        query = query.filter(models.LabPrep.protocol_id.in_([p.id for p in protocol_in]))

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if sort_by is not None:
        query = query.order_by(getattr(models.LabPrep, sort_by).desc() if descending else getattr(models.LabPrep, sort_by))

    if limit is not None:
        query = query.limit(limit)
    if offset is not None:
        query = query.offset(offset)

    lab_preps = query.all()

    if not persist_session:
        self.close_session()
    return lab_preps, n_pages


def get_next_protocol_identifier(self, protocol: LabProtocolEnum) -> str:
    if not (persist_session := self._session is not None):
        self.open_session()

    if not protocol.identifier:
        raise TypeError(f"Pool type {protocol} does not have an identifier")

    n_pools = self._session.query(models.LabPrep).where(
        models.LabPrep.protocol_id == protocol.id
    ).count()

    identifier = f"{protocol.identifier}{n_pools + 1:04d}"

    if not persist_session:
        self.close_session()

    return identifier


def update_lab_prep(
    self, lab_prep: models.LabPrep
) -> models.LabPrep:
    if not (persist_session := self._session is not None):
        self.open_session()

    self._session.add(lab_prep)
    self._session.commit()
    self._session.refresh(lab_prep)

    if not persist_session:
        self.close_session()
    return lab_prep


def add_library_to_prep(
    self, lab_prep_id: int, library_id: int
) -> models.LabPrep:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (lab_prep := self._session.get(models.LabPrep, lab_prep_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Lab prep with id '{lab_prep_id}', not found.")
    
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id '{library_id}', not found.")
    
    library.status = LibraryStatus.PREPARING
    lab_prep.libraries.append(library)

    self._session.add(lab_prep)
    self._session.commit()
    self._session.refresh(lab_prep)

    if not persist_session:
        self.close_session()

    return lab_prep


def remove_library_from_prep(
    self, lab_prep_id: int, library_id: int
) -> models.LabPrep:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (lab_prep := self._session.get(models.LabPrep, lab_prep_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Lab prep with id '{lab_prep_id}', not found.")
    
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id '{library_id}', not found.")
    
    if library.status == LibraryStatus.PREPARING:
        library.status = LibraryStatus.ACCEPTED
    
    lab_prep.libraries.remove(library)

    self._session.add(lab_prep)
    self._session.commit()
    self._session.refresh(lab_prep)

    if not persist_session:
        self.close_session()

    return lab_prep
