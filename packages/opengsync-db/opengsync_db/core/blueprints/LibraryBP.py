import math
from typing import Optional, Callable, Iterator

import sqlalchemy as sa
from sqlalchemy.orm.query import Query
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.orm import aliased

from ... import models, PAGE_LIMIT
from ...categories import (
    LibraryType, LibraryStatus, LibraryStatus, GenomeRef, PoolStatus,
    AccessType, AccessType, ServiceType, IndexType, MUXType, BarcodeOrientation,
    UserRole
)
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class LibraryBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query,
        user_id: int | None = None, sample_id: int | None = None,
        experiment_id: int | None = None, seq_request_id: int | None = None,
        service_type: Optional[ServiceType] = None,
        pool_id: int | None = None, lab_prep_id: int | None = None,
        in_lab_prep: bool | None = None,
        project_id: int | None = None,
        type_in: Optional[list[LibraryType]] = None,
        status_in: Optional[list[LibraryStatus]] = None,
        pooled: bool | None = None, status: Optional[LibraryStatus] = None,
        custom_query: Callable[[Query], Query] | None = None,
    ) -> Query:
        if user_id is not None:
            query = query.where(models.Library.owner_id == user_id)

        if seq_request_id is not None:
            query = query.where(models.Library.seq_request_id == seq_request_id)

        if sample_id is not None:
            query = query.where(
                sa.exists().where(
                    (models.links.SampleLibraryLink.sample_id == sample_id) &
                    (models.Library.id == models.links.SampleLibraryLink.library_id)
                )
            )

        if project_id is not None:
            query = query.where(
                sa.exists().where(
                    (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
                    (models.Library.id == models.links.SampleLibraryLink.library_id) &
                    (models.Sample.project_id == project_id)
                )
            )

        if experiment_id is not None:
            query = query.where(models.Library.experiment_id == experiment_id)

        if pooled is not None:
            if pooled:
                query = query.where(models.Library.pool_id.is_not(None))
            else:
                query = query.where(models.Library.pool_id.is_(None))

        if status is not None:
            query = query.where(models.Library.status_id == status.id)

        if pool_id is not None:
            query = query.where(models.Library.pool_id == pool_id)

        if service_type is not None:
            query = query.where(models.Library.service_type_id == service_type.id)

        if lab_prep_id is not None:
            query = query.where(models.Library.lab_prep_id == lab_prep_id)

        if in_lab_prep is not None:
            if in_lab_prep:
                query = query.where(models.Library.lab_prep_id != None) # noqa
            else:
                query = query.where(models.Library.lab_prep_id == None) # noqa

        if type_in is not None:
            query = query.where(models.Library.type_id.in_([t.id for t in type_in]))

        if status_in is not None:
            query = query.where(models.Library.status_id.in_([s.id for s in status_in]))

        if custom_query is not None:
            query = custom_query(query)

        return query

    @DBBlueprint.transaction
    def create(
        self,
        name: str,
        sample_name: str,
        library_type: LibraryType,
        owner_id: int,
        seq_request_id: int,
        genome_ref: GenomeRef,
        service_type: ServiceType,
        original_library_id: int | None = None,
        properties: Optional[dict | None] = None,
        index_type: IndexType | None = None,
        nuclei_isolation: bool = False,
        mux_type: MUXType | None = None,
        pool_id: int | None = None,
        lab_prep_id: int | None = None,
        seq_depth_requested: float | None = None,
        status: Optional[LibraryStatus] = None,
        flush: bool = True
    ) -> models.Library:
        if self.db.session.get(models.User, owner_id) is None:
            raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")
        
        if seq_request_id is not None:
            if (seq_request := self.db.session.get(models.SeqRequest, seq_request_id)) is None:
                raise exceptions.ElementDoesNotExist(f"Seq request with id {seq_request_id} does not exist")
            self.db.session.add(seq_request)

        if status is None:
            if pool_id is not None:
                if (pool := self.db.session.get(models.Pool, pool_id)) is None:
                    raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
                self.db.session.add(pool)
                status = LibraryStatus.POOLED
            else:
                status = LibraryStatus.DRAFT

        if original_library_id is not None:
            if self.db.session.get(models.Library, original_library_id) is None:
                raise exceptions.ElementDoesNotExist(f"Original library with id {original_library_id} does not exist")
            clone_number = self.get_number_of_cloned_libraries(original_library_id) + 1
        else:
            clone_number = 0
            
        library = models.Library(
            name=name.strip(),
            sample_name=sample_name,
            seq_request_id=seq_request_id,
            genome_ref_id=genome_ref.id if genome_ref is not None else None,
            type_id=library_type.id,
            service_type_id=service_type.id,
            owner_id=owner_id,
            pool_id=pool_id,
            lab_prep_id=lab_prep_id,
            status_id=status.id,
            index_type_id=index_type.id if index_type is not None else None,
            properties=properties if properties is not None and len(properties) > 0 else None,
            seq_depth_requested=seq_depth_requested,
            nuclei_isolation=nuclei_isolation,
            mux_type_id=mux_type.id if mux_type is not None else None,
            clone_number=clone_number,
            original_library_id=original_library_id,
        )

        self.db.session.add(library)

        if flush:
            self.db.flush()

        return library

    @DBBlueprint.transaction
    def get(self, library_id: int, options: ExecutableOption | None = None) -> models.Library | None:
        if options is None:
            library = self.db.session.get(models.Library, library_id)
        else:
            library = self.db.session.query(models.Library).options(options).filter(models.Library.id == library_id).first()
        return library

    @DBBlueprint.transaction
    def find(
        self,
        user_id: int | None = None,
        sample_id: int | None = None,
        experiment_id: int | None = None,
        seq_request_id: int | None = None,
        service_type: ServiceType | None = None,
        pool_id: int | None = None,
        lab_prep_id: int | None = None,
        in_lab_prep: bool | None = None,
        project_id: int | None = None,
        type_in: list[LibraryType] | None = None,
        status_in: list[LibraryStatus] | None = None,
        pooled: bool | None = None,
        status: LibraryStatus | None = None,
        name: str | None = None,
        id: int | None = None,
        pool_name: str | None = None,
        custom_query: Callable[[Query], Query] | None = None,
        sort_by: str | None = None, descending: bool = False,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        page: int | None = None,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.Library], int | None]:

        query = self.db.session.query(models.Library)
        query = LibraryBP.where(
            query,
            user_id=user_id, sample_id=sample_id, experiment_id=experiment_id,
            seq_request_id=seq_request_id, service_type=service_type,
            pool_id=pool_id, lab_prep_id=lab_prep_id, in_lab_prep=in_lab_prep,
            type_in=type_in, status_in=status_in, pooled=pooled, status=status,
            custom_query=custom_query, project_id=project_id
        )
        
        if options is not None:
            query = query.options(options)

        if sort_by is not None:
            attr = getattr(models.Library, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        if id is not None:
            query = query.filter(models.Library.id == id)
        elif name is not None:
            query = query.order_by(
                sa.func.similarity(models.Library.name, name).desc()
            )
        elif pool_name is not None:
            query = query.join(
                models.Pool,
                models.Pool.id == models.Library.pool_id
            ).order_by(
                sa.func.similarity(models.Pool.name, pool_name).desc()
            )

        if page is not None:
            if limit is None:
                raise ValueError("Limit must be provided when page is provided")
            
            count = query.count()
            n_pages = math.ceil(count / limit)
            query = query.offset(min(page, max(0, n_pages - 1)) * limit)
        else:
            n_pages = None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)
        
        libraries = query.all()

        return libraries, n_pages

    @DBBlueprint.transaction
    def delete(
        self, library: models.Library, delete_orphan_samples: bool = True,
        flush: bool = True
    ):
        if delete_orphan_samples:
            SLL1 = aliased(models.links.SampleLibraryLink)
            SLL2 = aliased(models.links.SampleLibraryLink)

            subquery = (
                self.db.session.query(models.Sample.id)
                .join(SLL1, SLL1.sample_id == models.Sample.id)  # for counting
                .group_by(models.Sample.id)
                .having(sa.func.count(SLL1.library_id) == 1)
                .join(SLL2, SLL2.sample_id == models.Sample.id)  # for filtering by library_id
                .filter(SLL2.library_id == library.id)
                .subquery()
            )

            self.db.session.query(models.Sample).filter(
                models.Sample.id.in_(sa.select(subquery.c.id))
            ).delete(synchronize_session="fetch")

        self.db.session.delete(library)

        if flush:
            self.db.flush()
        
        self.db.features.delete_orphan(flush=flush)

    @DBBlueprint.transaction
    def update(self, library: models.Library):
        self.db.session.add(library)

    def get_number_of_cloned_libraries(self, original_library_id: int) -> int:
        count = self.db.session.query(models.Library).where(
            models.Library.original_library_id == original_library_id
        ).count()
        return count

    @DBBlueprint.transaction
    def query(
        self,
        name: str | None = None, owner: str | None = None,
        user_id: int | None = None,
        sample_id: int | None = None,
        experiment_id: int | None = None,
        seq_request_id: int | None = None,
        service_type: Optional[ServiceType] = None,
        pool_id: int | None = None,
        lab_prep_id: int | None = None,
        in_lab_prep: bool | None = None,
        type_in: Optional[list[LibraryType]] = None,
        status_in: Optional[list[LibraryStatus]] = None,
        pooled: bool | None = None,
        status: Optional[LibraryStatus] = None,
        custom_query: Callable[[Query], Query] | None = None,
        limit: int | None = PAGE_LIMIT,
    ) -> list[models.Library]:
        query = self.db.session.query(models.Library)

        query = LibraryBP.where(
            query,
            user_id=user_id, sample_id=sample_id, experiment_id=experiment_id,
            seq_request_id=seq_request_id, service_type=service_type,
            pool_id=pool_id, lab_prep_id=lab_prep_id, in_lab_prep=in_lab_prep,
            type_in=type_in, status_in=status_in, pooled=pooled, status=status,
            custom_query=custom_query
        )

        if name is not None:
            query = query.order_by(
                sa.func.similarity(models.Library.name, name).desc()
            )
        elif owner is not None:
            query = query.join(
                models.User,
                models.User.id == models.Library.owner_id
            )
            query = query.order_by(
                sa.func.similarity(models.User.first_name + ' ' + models.User.last_name, owner).desc()
            )
        else:
            raise ValueError("At least one of 'name' or 'owner' must be provided")

        if limit is not None:
            query = query.limit(limit)

        libraries = query.all()

        return libraries

    @DBBlueprint.transaction
    def add_to_pool(
        self, library_id: int, pool_id: int,
        flush: bool = True
    ) -> models.Library:

        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

        if library.pool_id is not None:
            raise exceptions.LinkAlreadyExists(f"Library with id {library_id} is already pooled")
            
        library.pool_id = pool_id
        self.db.session.add(library)

        if flush:
            self.db.flush()

        return library

    @DBBlueprint.transaction
    def set_seq_quality(
        self, library_id: int | None, experiment_id: int, lane: int, num_reads: int, qc: dict | None = None,
    ) -> models.SeqQuality:
        if library_id is not None:
            if (library := self.db.session.get(models.Library, library_id)) is None:
                raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
            
            if library.status < LibraryStatus.SEQUENCED:
                library.status = LibraryStatus.SEQUENCED
            if library.pool is not None:
                if library.pool.status < PoolStatus.SEQUENCED:
                    library.pool.status = PoolStatus.SEQUENCED
            
            self.db.session.add(library)
            
        if (quality := self.db.session.query(models.SeqQuality).where(
            (models.SeqQuality.library_id == library_id) if library_id is not None else (models.SeqQuality.library_id.is_(None)),
            models.SeqQuality.experiment_id == experiment_id,
            models.SeqQuality.lane == lane,
        ).first()) is not None:
            quality.num_reads = num_reads
            quality.qc = qc
        else:
            quality = models.SeqQuality(
                library_id=library_id, lane=lane, experiment_id=experiment_id,
                num_reads=num_reads, qc=qc
            )

        self.db.session.add(quality)

        return quality
    
    @DBBlueprint.transaction
    def remove_seq_quality(
        self, library_id: int | None, experiment_id: int, lane: int, flush: bool = True
    ):
        quality_query = self.db.session.query(models.SeqQuality).where(
            (models.SeqQuality.library_id == library_id) if library_id is not None else (models.SeqQuality.library_id.is_(None)),
            models.SeqQuality.experiment_id == experiment_id,
            models.SeqQuality.lane == lane,
        )
        quality_query.delete(synchronize_session="fetch")

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def add_index(
        self, library_id: int,
        index_kit_i7_id: Optional[int], name_i7: Optional[str], sequence_i7: Optional[str],
        index_kit_i5_id: Optional[int], name_i5: Optional[str], sequence_i5: Optional[str],
        orientation: Optional[BarcodeOrientation],
        flush: bool = True
    ) -> models.Library:

        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
        
        if index_kit_i7_id is not None:
            if self.db.session.get(models.IndexKit, index_kit_i7_id) is None:
                raise exceptions.ElementDoesNotExist(f"Index kit with id {index_kit_i7_id} does not exist")
            
        if index_kit_i5_id is not None:
            if self.db.session.get(models.IndexKit, index_kit_i5_id) is None:
                raise exceptions.ElementDoesNotExist(f"Index kit with id {index_kit_i5_id} does not exist")

        library.indices.append(models.LibraryIndex(
            library_id=library_id,
            name_i7=name_i7,
            sequence_i7=sequence_i7,
            name_i5=name_i5,
            sequence_i5=sequence_i5,
            index_kit_i7_id=index_kit_i7_id,
            index_kit_i5_id=index_kit_i5_id,
            _orientation=orientation.id if orientation is not None else None,
        ))

        self.db.session.add(library)

        if flush:
            self.db.flush()

        return library

    @DBBlueprint.transaction
    def remove_indices(self, library_id: int, flush: bool = True) -> models.Library:

        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

        for index in library.indices:
            self.db.session.delete(index)

        library.indices = []
        self.db.session.add(library)

        if flush:
            self.db.flush()

        return library

    @DBBlueprint.transaction
    def get_access_type(self, library: models.Library, user: models.User) -> AccessType:
        if user.role == UserRole.DEACTIVATED:
            return AccessType.NONE
        if user.is_admin():
            return AccessType.ADMIN
        if user.is_insider():
            return AccessType.INSIDER
        if library.owner_id == user.id:
            return AccessType.OWNER
        
        has_access: bool = self.db.session.query(
            sa.exists().where(
                (models.links.UserAffiliation.user_id == user.id) &
                (models.links.UserAffiliation.group_id == library.seq_request.group_id)
            )
        ).scalar()

        if has_access:
            return AccessType.EDIT

        return AccessType.NONE

    @DBBlueprint.transaction
    def clone(
        self, library_id: int, seq_request_id: int, indexed: bool, status: LibraryStatus
    ) -> models.Library:

        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

        cloned_library = self.create(
            name=library.name,
            sample_name=library.sample_name,
            library_type=library.type,
            seq_request_id=seq_request_id,
            owner_id=library.owner_id,
            genome_ref=library.genome_ref,
            service_type=library.service_type,
            mux_type=library.mux_type,
            properties=library.properties,
            index_type=library.index_type,
            nuclei_isolation=library.nuclei_isolation,
            original_library_id=library.original_library_id if library.original_library_id is not None else library.id,
            status=status
        )

        for sample_link in library.sample_links:
            self.db.links.link_sample_library(
                sample_id=sample_link.sample_id,
                library_id=cloned_library.id,
                mux=sample_link.mux if sample_link.mux is not None else None,
            )

        for feature in library.features:
            self.db.links.link_feature_library(
                feature_id=feature.id,
                library_id=cloned_library.id
            )

        if indexed:
            for index in library.indices:
                self.add_index(
                    library_id=cloned_library.id,
                    index_kit_i7_id=index.index_kit_i7_id,
                    name_i7=index.name_i7,
                    sequence_i7=index.sequence_i7,
                    index_kit_i5_id=index.index_kit_i5_id,
                    name_i5=index.name_i5,
                    sequence_i5=index.sequence_i5,
                    orientation=index.orientation,
                )

        return cloned_library
    
    @DBBlueprint.transaction
    def __getitem__(self, id: int) -> models.Library:
        if (library := self.db.session.get(models.Library, id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {id} does not exist")
        return library

    @DBBlueprint.transaction
    def iter(
        self,
        user_id: int | None = None,
        sample_id: int | None = None,
        experiment_id: int | None = None,
        seq_request_id: int | None = None,
        service_type: Optional[ServiceType] = None,
        pool_id: int | None = None,
        lab_prep_id: int | None = None,
        in_lab_prep: bool | None = None,
        project_id: int | None = None,
        type_in: Optional[list[LibraryType]] = None,
        status_in: Optional[list[LibraryStatus]] = None,
        pooled: bool | None = None,
        status: Optional[LibraryStatus] = None,
        custom_query: Callable[[Query], Query] | None = None,
        order_by: str | None = "id",
        limit: int | None = None,
        chunk_size: int = 1000
    ) -> Iterator[models.Library]:
        """
        Iterator that yields libraries based on query parameters.
        Uses chunking to handle large datasets efficiently.
        """
        query = self.db.session.query(models.Library)
        if order_by is not None:
            attr = getattr(models.Library, order_by)
            query = query.order_by(sa.nulls_last(attr))
        query = LibraryBP.where(
            query,
            user_id=user_id, sample_id=sample_id, experiment_id=experiment_id,
            seq_request_id=seq_request_id, service_type=service_type,
            pool_id=pool_id, lab_prep_id=lab_prep_id, in_lab_prep=in_lab_prep,
            type_in=type_in, status_in=status_in, pooled=pooled, status=status,
            custom_query=custom_query, project_id=project_id
        )
        offset = 0
        while True:
            chunk = query.limit(chunk_size).offset(offset).all()
            if not chunk:
                break
            
            for library in chunk:
                yield library
            
            if limit and offset + chunk_size >= limit:
                break
                
            offset += chunk_size

    @DBBlueprint.transaction
    def __iter__(self) -> Iterator[models.Library]:
        return self.iter()
    
    @DBBlueprint.transaction
    def __len__(self) -> int:
        return self.db.session.query(models.Library).count()
