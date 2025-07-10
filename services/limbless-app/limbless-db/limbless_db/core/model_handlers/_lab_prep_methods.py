import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT, LAB_PROTOCOL_START_NUMBER
from ...categories import LabProtocolEnum, LibraryStatus, PrepStatusEnum, AssayTypeEnum
from .. import exceptions


def create_lab_prep(
    self: "DBHandler",
    name: str | None,
    creator_id: int,
    protocol: LabProtocolEnum,
    assay_type: AssayTypeEnum
) -> models.LabPrep:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (creator := self.session.get(models.User, creator_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{creator_id}', not found.")
    
    number = self.get_next_protocol_number(protocol)

    if not name:
        name = f"{protocol.identifier}{number + LAB_PROTOCOL_START_NUMBER:04d}"

    lab_prep = models.LabPrep(
        name=name.strip(),
        prep_number=number,
        creator_id=creator.id,
        protocol_id=protocol.id,
        assay_type_id=assay_type.id,
    )

    self.session.add(lab_prep)
    self.session.commit()
    self.session.refresh(lab_prep)

    if not persist_session:
        self.close_session()
    return lab_prep


def get_lab_prep(self: "DBHandler", lab_prep_id: int) -> models.LabPrep | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    lab_prep = self.session.get(models.LabPrep, lab_prep_id)

    if not persist_session:
        self.close_session()

    return lab_prep


def get_lab_preps(
    self: "DBHandler", procotol: Optional[LabProtocolEnum] = None,
    protocol_in: Optional[list[LabProtocolEnum]] = None,
    status: Optional[PrepStatusEnum] = None,
    status_in: Optional[list[PrepStatusEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    count_pages: bool = False
) -> tuple[list[models.LabPrep], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.LabPrep)

    if procotol is not None:
        query = query.where(models.LabPrep.protocol_id == procotol.id)
    elif protocol_in is not None:
        query = query.where(models.LabPrep.protocol_id.in_([p.id for p in protocol_in]))

    if status is not None:
        query = query.where(models.LabPrep.status_id == status.id)
    elif status_in is not None:
        query = query.where(models.LabPrep.status_id.in_([s.id for s in status_in]))

    n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

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


def query_lab_preps(
    self: "DBHandler", name: Optional[str] = None, creator: Optional[str] = None,
    procotol: Optional[LabProtocolEnum] = None,
    protocol_in: Optional[list[LabProtocolEnum]] = None,
    status: Optional[PrepStatusEnum] = None,
    status_in: Optional[list[PrepStatusEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT
) -> list[models.LabPrep]:
    if not (persist_session := self._session is not None):
        self.open_session()
    
    query = self.session.query(models.LabPrep)

    if procotol is not None:
        query = query.where(models.LabPrep.protocol_id == procotol.id)
    elif protocol_in is not None:
        query = query.where(models.LabPrep.protocol_id.in_([p.id for p in protocol_in]))

    if status is not None:
        query = query.where(models.LabPrep.status_id == status.id)
    elif status_in is not None:
        query = query.where(models.LabPrep.status_id.in_([s.id for s in status_in]))

    if name is not None:
        query = query.order_by(
            sa.func.similarity(models.LabPrep.name, name).desc()
        )
    elif creator is not None:
        query = query.join(
            models.User,
            models.User.id == models.LabPrep.creator_id
        )
        query = query.order_by(
            sa.func.similarity(models.User.first_name + ' ' + models.User.last_name, creator).desc()
        )
    else:
        raise ValueError("Either 'name' or 'owner' must be provided.")
    
    if limit is not None:
        query = query.limit(limit)

    lab_preps = query.all()

    if not persist_session:
        self.close_session()

    return lab_preps


def get_next_protocol_number(self: "DBHandler", protocol: LabProtocolEnum) -> int:
    if not (persist_session := self._session is not None):
        self.open_session()

    if not protocol.identifier:
        raise TypeError(f"Pool type {protocol} does not have an identifier")

    if (latest_prep := self.session.query(models.LabPrep).where(
        models.LabPrep.protocol_id == protocol.id
    ).order_by(
        models.LabPrep.prep_number.desc()
    ).first()) is not None:
        prep_number = latest_prep.prep_number + 1
    else:
        prep_number = 1

    if not persist_session:
        self.close_session()

    return prep_number


def update_lab_prep(
    self: "DBHandler", lab_prep: models.LabPrep
) -> models.LabPrep:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(lab_prep)
    self.session.commit()
    self.session.refresh(lab_prep)

    if not persist_session:
        self.close_session()
    return lab_prep


def add_library_to_prep(
    self: "DBHandler", lab_prep_id: int, library_id: int
) -> models.LabPrep:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (lab_prep := self.session.get(models.LabPrep, lab_prep_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Lab prep with id '{lab_prep_id}', not found.")
    
    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id '{library_id}', not found.")
    
    library.status = LibraryStatus.PREPARING
    lab_prep.libraries.append(library)

    self.session.add(lab_prep)
    self.session.commit()
    self.session.refresh(lab_prep)

    if not persist_session:
        self.close_session()

    return lab_prep


def remove_library_from_prep(
    self: "DBHandler", lab_prep_id: int, library_id: int
) -> models.LabPrep:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (lab_prep := self.session.get(models.LabPrep, lab_prep_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Lab prep with id '{lab_prep_id}', not found.")
    
    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id '{library_id}', not found.")
    
    if library.status == LibraryStatus.PREPARING:
        library.status = LibraryStatus.ACCEPTED
    
    lab_prep.libraries.remove(library)

    self.session.add(lab_prep)
    self.session.commit()
    self.session.refresh(lab_prep)

    if not persist_session:
        self.close_session()

    return lab_prep