import math
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.sql.base import ExecutableOption

from ... import models, PAGE_LIMIT
from ...categories import LabProtocolEnum, LibraryStatus, PrepStatusEnum, AssayTypeEnum
from ..DBBlueprint import DBBlueprint
from .. import exceptions


class LabPrepBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self,
        name: str | None,
        creator_id: int,
        protocol: LabProtocolEnum,
        assay_type: AssayTypeEnum,
        flush: bool = True
    ) -> models.LabPrep:
        if (creator := self.db.session.get(models.User, creator_id)) is None:
            raise exceptions.ElementDoesNotExist(f"User with id '{creator_id}', not found.")
        
        number = self.get_next_protocol_number(protocol)

        if not name:
            name = f"{protocol.identifier}{number:04d}"

        lab_prep = models.LabPrep(
            name=name.strip(),
            prep_number=number,
            creator_id=creator.id,
            protocol_id=protocol.id,
            assay_type_id=assay_type.id,
        )

        self.db.session.add(lab_prep)

        if flush:
            self.db.flush()
        return lab_prep

    @DBBlueprint.transaction
    def get(self, lab_prep_id: int, options: ExecutableOption | None = None) -> models.LabPrep | None:
        if options is not None:
            lab_prep = self.db.session.query(models.LabPrep).options(options).filter(models.LabPrep.id == lab_prep_id).first()
        else:
            lab_prep = self.db.session.get(models.LabPrep, lab_prep_id)
        return lab_prep

    @DBBlueprint.transaction
    def find(
        self, procotol: Optional[LabProtocolEnum] = None,
        protocol_in: Optional[list[LabProtocolEnum]] = None,
        status: Optional[PrepStatusEnum] = None,
        status_in: Optional[list[PrepStatusEnum]] = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        count_pages: bool = False,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.LabPrep], int | None]:
        query = self.db.session.query(models.LabPrep)

        if procotol is not None:
            query = query.where(models.LabPrep.protocol_id == procotol.id)
        elif protocol_in is not None:
            query = query.where(models.LabPrep.protocol_id.in_([p.id for p in protocol_in]))

        if status is not None:
            query = query.where(models.LabPrep.status_id == status.id)
        elif status_in is not None:
            query = query.where(models.LabPrep.status_id.in_([s.id for s in status_in]))

        if options is not None:
            query = query.options(options)
            
        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if sort_by is not None:
            query = query.order_by(getattr(models.LabPrep, sort_by).desc() if descending else getattr(models.LabPrep, sort_by))

        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)

        lab_preps = query.all()
        return lab_preps, n_pages

    @DBBlueprint.transaction
    def delete(self, lab_prep_id: int, flush: bool = True) -> None:
        if (lab_prep := self.db.session.get(models.LabPrep, lab_prep_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Lab prep with id '{lab_prep_id}', not found.")

        for library in lab_prep.libraries:
            library.lab_prep_id = None

        for pool in lab_prep.pools:
            for library in pool.libraries:
                library.pool_id = None

        for plate in lab_prep.plates:
            for link in plate.sample_links:
                self.db.session.delete(link)
            self.db.session.delete(plate)

        self.db.session.delete(lab_prep)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def query(
        self, name: Optional[str] = None, creator: Optional[str] = None,
        procotol: Optional[LabProtocolEnum] = None,
        protocol_in: Optional[list[LabProtocolEnum]] = None,
        status: Optional[PrepStatusEnum] = None,
        status_in: Optional[list[PrepStatusEnum]] = None,
        limit: int | None = PAGE_LIMIT
    ) -> list[models.LabPrep]:
        query = self.db.session.query(models.LabPrep)

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
        return lab_preps

    @DBBlueprint.transaction
    def get_next_protocol_number(self, protocol: LabProtocolEnum) -> int:
        if not protocol.identifier:
            raise TypeError(f"Pool type {protocol} does not have an identifier")

        if (latest_prep := self.db.session.query(models.LabPrep).where(
            models.LabPrep.protocol_id == protocol.id
        ).order_by(
            models.LabPrep.prep_number.desc()
        ).first()) is not None:
            prep_number = latest_prep.prep_number + 1
        else:
            prep_number = self.db.lab_protocol_start_number
        return prep_number

    @DBBlueprint.transaction
    def update(self, lab_prep: models.LabPrep):
        self.db.session.add(lab_prep)

    @DBBlueprint.transaction
    def add_library(
        self, lab_prep_id: int, library_id: int
    ) -> models.LabPrep:
        if (lab_prep := self.db.session.get(models.LabPrep, lab_prep_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Lab prep with id '{lab_prep_id}', not found.")
        
        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id '{library_id}', not found.")
        
        library.status = LibraryStatus.PREPARING
        lab_prep.libraries.append(library)

        self.db.session.add(lab_prep)
        return lab_prep

    @DBBlueprint.transaction
    def remove_library(
        self, lab_prep_id: int, library_id: int, flush: bool = True
    ) -> models.LabPrep:
        if (lab_prep := self.db.session.get(models.LabPrep, lab_prep_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Lab prep with id '{lab_prep_id}', not found.")
        
        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id '{library_id}', not found.")
        
        if library.status == LibraryStatus.PREPARING:
            library.status = LibraryStatus.ACCEPTED
        
        lab_prep.libraries.remove(library)
        self.db.session.add(lab_prep)
        if flush:
            self.db.flush()
        return lab_prep
    
    @DBBlueprint.transaction
    def __getitem__(self, id: int) -> models.LabPrep:
        if (lab_prep := self.db.session.get(models.LabPrep, id)) is None:
            raise exceptions.ElementDoesNotExist(f"Lab prep with id '{id}', not found.")
        return lab_prep