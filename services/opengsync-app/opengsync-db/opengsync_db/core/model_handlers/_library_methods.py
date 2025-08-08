import math
from typing import Optional, TYPE_CHECKING, Callable

import sqlalchemy as sa
from sqlalchemy.sql.operators import or_, and_  # noqa F401
from sqlalchemy.orm.query import Query
from sqlalchemy.orm import aliased

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from ...categories import (
    LibraryTypeEnum, LibraryStatus, LibraryStatusEnum, GenomeRefEnum, PoolStatus,
    AccessType, AccessTypeEnum, AssayTypeEnum, IndexTypeEnum, MUXTypeEnum
)
from .. import exceptions


def create_library(
    self: "DBHandler",
    name: str,
    sample_name: str,
    library_type: LibraryTypeEnum,
    owner_id: int,
    seq_request_id: int,
    genome_ref: GenomeRefEnum,
    assay_type: AssayTypeEnum,
    original_library_id: int | None = None,
    properties: Optional[dict | None] = None,
    index_type: IndexTypeEnum | None = None,
    nuclei_isolation: bool = False,
    mux_type: MUXTypeEnum | None = None,
    pool_id: int | None = None,
    lab_prep_id: int | None = None,
    seq_depth_requested: Optional[float] = None,
    status: Optional[LibraryStatusEnum] = None,
    flush: bool = True
) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self.session.get(models.User, owner_id) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")
    
    if seq_request_id is not None:
        if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Seq request with id {seq_request_id} does not exist")
        self.session.add(seq_request)

    if status is None:
        if pool_id is not None:
            if (pool := self.session.get(models.Pool, pool_id)) is None:
                raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
            self.session.add(pool)
            status = LibraryStatus.POOLED
        else:
            status = LibraryStatus.DRAFT

    if original_library_id is not None:
        if self.session.get(models.Library, original_library_id) is None:
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
        assay_type_id=assay_type.id,
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

    self.session.add(library)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()

    return library


def get_library(self: "DBHandler", library_id: int) -> models.Library | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    library = self.session.get(models.Library, library_id)
    
    if not persist_session:
        self.close_session()
    return library


def where(
    query: Query,
    user_id: int | None = None, sample_id: int | None = None,
    experiment_id: int | None = None, seq_request_id: int | None = None,
    assay_type: Optional[AssayTypeEnum] = None,
    pool_id: int | None = None, lab_prep_id: int | None = None,
    in_lab_prep: Optional[bool] = None,
    project_id: int | None = None,
    type_in: Optional[list[LibraryTypeEnum]] = None,
    status_in: Optional[list[LibraryStatusEnum]] = None,
    pooled: Optional[bool] = None, status: Optional[LibraryStatusEnum] = None,
    custom_query: Callable[[Query], Query] | None = None,
) -> Query:
    if user_id is not None:
        query = query.where(
            models.Library.owner_id == user_id
        )

    if seq_request_id is not None:
        query = query.where(
            models.Library.seq_request_id == seq_request_id
        )

    if sample_id is not None or project_id is not None:
        query = query.join(
            models.links.SampleLibraryLink,
            models.links.SampleLibraryLink.library_id == models.Library.id,
        )
        
        if sample_id is not None:
            query = query.where(models.links.SampleLibraryLink.sample_id == sample_id)

        if project_id is not None:
            query = query.join(
                models.Sample,
                models.Sample.id == models.links.SampleLibraryLink.sample_id,
            ).where(models.Sample.project_id == project_id)

            query = query.distinct(models.Library.id)

    if experiment_id is not None:
        query = query.where(models.Library.experiment_id == experiment_id)

    if pooled is not None:
        if pooled:
            query = query.where(
                models.Library.pool_id.is_not(None)
            )
        else:
            query = query.where(
                models.Library.pool_id.is_(None)
            )

    if status is not None:
        query = query.where(
            models.Library.status_id == status.id
        )

    if pool_id is not None:
        query = query.where(
            models.Library.pool_id == pool_id
        )

    if assay_type is not None:
        query = query.where(models.Library.assay_type_id == assay_type.id)

    if lab_prep_id is not None:
        query = query.where(models.Library.lab_prep_id == lab_prep_id)

    if in_lab_prep is not None:
        if in_lab_prep:
            query = query.where(models.Library.lab_prep_id != None) # noqa
        else:
            query = query.where(models.Library.lab_prep_id == None) # noqa

    if type_in is not None:
        query = query.where(
            models.Library.type_id.in_([t.id for t in type_in])
        )

    if status_in is not None:
        query = query.where(
            models.Library.status_id.in_([s.id for s in status_in])
        )

    if custom_query is not None:
        query = custom_query(query)

    return query
    

def get_libraries(
    self: "DBHandler",
    user_id: int | None = None,
    sample_id: int | None = None,
    experiment_id: int | None = None,
    seq_request_id: int | None = None,
    assay_type: Optional[AssayTypeEnum] = None,
    pool_id: int | None = None,
    lab_prep_id: int | None = None,
    in_lab_prep: Optional[bool] = None,
    project_id: int | None = None,
    type_in: Optional[list[LibraryTypeEnum]] = None,
    status_in: Optional[list[LibraryStatusEnum]] = None,
    pooled: Optional[bool] = None,
    status: Optional[LibraryStatusEnum] = None,
    custom_query: Callable[[Query], Query] | None = None,
    sort_by: Optional[str] = None, descending: bool = False,
    limit: int | None = PAGE_LIMIT, offset: int | None = None,
    count_pages: bool = False
) -> tuple[list[models.Library], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Library)
    query = where(
        query,
        user_id=user_id, sample_id=sample_id, experiment_id=experiment_id,
        seq_request_id=seq_request_id, assay_type=assay_type,
        pool_id=pool_id, lab_prep_id=lab_prep_id, in_lab_prep=in_lab_prep,
        type_in=type_in, status_in=status_in, pooled=pooled, status=status,
        custom_query=custom_query, project_id=project_id
    )

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
    
    libraries = query.all()

    if not persist_session:
        self.close_session()

    return libraries, n_pages


def delete_library(
    self: "DBHandler", library_id: int, delete_orphan_samples: bool = True,
    flush: bool = True
):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if delete_orphan_samples:
        SLL1 = aliased(models.links.SampleLibraryLink)
        SLL2 = aliased(models.links.SampleLibraryLink)

        subquery = (
            self.session.query(models.Sample.id)
            .join(SLL1, SLL1.sample_id == models.Sample.id)  # for counting
            .group_by(models.Sample.id)
            .having(sa.func.count(SLL1.library_id) == 1)
            .join(SLL2, SLL2.sample_id == models.Sample.id)  # for filtering by library_id
            .filter(SLL2.library_id == library_id)
            .subquery()
        )

        self.session.query(models.Sample).filter(
            models.Sample.id.in_(sa.select(subquery.c.id))
        ).delete(synchronize_session="fetch")

    self.session.delete(library)

    if flush:
        self.session.flush()

    self.delete_orphan_features(flush=flush)

    if not persist_session:
        self.close_session()


def update_library(self: "DBHandler", library: models.Library) -> models.Library:
    
    if not (persist_session := self._session is not None):
        self.open_session()
    
    self.session.add(library)

    if not persist_session:
        self.close_session()
    return library


def get_number_of_cloned_libraries(self: "DBHandler", original_library_id: int) -> int:
    if not (persist_session := self._session is not None):
        self.open_session()

    count = self.session.query(models.Library).where(
        models.Library.original_library_id == original_library_id
    ).count()

    if not persist_session:
        self.close_session()

    return count


def query_libraries(
    self: "DBHandler",
    name: Optional[str] = None, owner: Optional[str] = None,
    user_id: int | None = None,
    sample_id: int | None = None,
    experiment_id: int | None = None,
    seq_request_id: int | None = None,
    assay_type: Optional[AssayTypeEnum] = None,
    pool_id: int | None = None,
    lab_prep_id: int | None = None,
    in_lab_prep: Optional[bool] = None,
    type_in: Optional[list[LibraryTypeEnum]] = None,
    status_in: Optional[list[LibraryStatusEnum]] = None,
    pooled: Optional[bool] = None,
    status: Optional[LibraryStatusEnum] = None,
    custom_query: Callable[[Query], Query] | None = None,
    limit: int | None = PAGE_LIMIT,
) -> list[models.Library]:

    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Library)

    query = where(
        query,
        user_id=user_id, sample_id=sample_id, experiment_id=experiment_id,
        seq_request_id=seq_request_id, assay_type=assay_type,
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

    if not persist_session:
        self.close_session()

    return libraries


def add_library_to_pool(
    self: "DBHandler", library_id: int, pool_id: int,
    flush: bool = True
) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    if library.pool_id is not None:
        raise exceptions.LinkAlreadyExists(f"Library with id {library_id} is already pooled")
        
    library.pool_id = pool_id
    self.session.add(library)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()

    return library


def set_library_seq_quality(
    self: "DBHandler", library_id: Optional[int], experiment_id: int, lane: int,
    num_lane_reads: int, num_library_reads: int,
    mean_quality_pf_r1: float, q30_perc_r1: float,
    mean_quality_pf_i1: float, q30_perc_i1: float,
    mean_quality_pf_r2: Optional[float], q30_perc_r2: Optional[float],
    mean_quality_pf_i2: Optional[float], q30_perc_i2: Optional[float],
) -> models.SeqQuality:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    if library_id is not None:
        if (library := self.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
        
        library.status = LibraryStatus.SEQUENCED
        if library.pool is not None:
            library.pool.status = PoolStatus.SEQUENCED
        self.session.add(library)
        
    if (quality := self.session.query(models.SeqQuality).where(
        models.SeqQuality.library_id == library_id,
        models.SeqQuality.experiment_id == experiment_id,
        models.SeqQuality.lane == lane,
    ).first()) is not None:
        quality.num_lane_reads = num_lane_reads
        quality.num_library_reads = num_library_reads
        quality.mean_quality_pf_r1 = mean_quality_pf_r1
        quality.q30_perc_r1 = q30_perc_r1
        quality.mean_quality_pf_i1 = mean_quality_pf_i1
        quality.q30_perc_i1 = q30_perc_i1
        quality.mean_quality_pf_r2 = mean_quality_pf_r2
        quality.q30_perc_r2 = q30_perc_r2
        quality.mean_quality_pf_i2 = mean_quality_pf_i2
        quality.q30_perc_i2 = q30_perc_i2
    else:
        quality = models.SeqQuality(
            library_id=library_id, lane=lane, experiment_id=experiment_id,
            num_lane_reads=num_lane_reads, num_library_reads=num_library_reads,
            mean_quality_pf_r1=mean_quality_pf_r1, q30_perc_r1=q30_perc_r1,
            mean_quality_pf_i1=mean_quality_pf_i1, q30_perc_i1=q30_perc_i1,
            mean_quality_pf_r2=mean_quality_pf_r2, q30_perc_r2=q30_perc_r2,
            mean_quality_pf_i2=mean_quality_pf_i2, q30_perc_i2=q30_perc_i2,
        )

    self.session.add(quality)

    if not persist_session:
        self.close_session()

    return quality


def add_library_index(
    self: "DBHandler", library_id: int,
    index_kit_i7_id: Optional[int], name_i7: Optional[str], sequence_i7: Optional[str],
    index_kit_i5_id: Optional[int], name_i5: Optional[str], sequence_i5: Optional[str],
    flush: bool = True
) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if index_kit_i7_id is not None:
        if self.session.get(models.IndexKit, index_kit_i7_id) is None:
            raise exceptions.ElementDoesNotExist(f"Index kit with id {index_kit_i7_id} does not exist")
        
    if index_kit_i5_id is not None:
        if self.session.get(models.IndexKit, index_kit_i5_id) is None:
            raise exceptions.ElementDoesNotExist(f"Index kit with id {index_kit_i5_id} does not exist")

    library.indices.append(models.LibraryIndex(
        library_id=library_id,
        name_i7=name_i7,
        sequence_i7=sequence_i7,
        name_i5=name_i5,
        sequence_i5=sequence_i5,
        index_kit_i7_id=index_kit_i7_id,
        index_kit_i5_id=index_kit_i5_id
    ))

    self.session.add(library)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()

    return library


def remove_library_indices(self: "DBHandler", library_id: int, flush: bool = True) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    for index in library.indices:
        self.session.delete(index)

    library.indices = []
    self.session.add(library)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()

    return library


def get_user_library_access_type(
    self: "DBHandler", library_id: int, user_id: int
) -> AccessTypeEnum | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    access_type: Optional[AccessTypeEnum] = None

    if library.owner_id == user_id:
        access_type = AccessType.OWNER
    elif library.seq_request.group_id is not None:
        if self.session.query(models.links.UserAffiliation).where(
            models.links.UserAffiliation.user_id == user_id,
            models.links.UserAffiliation.group_id == library.seq_request.group_id
        ).first() is not None:
            access_type = AccessType.EDIT

    if not persist_session:
        self.close_session()

    return access_type


def clone_library(
    self: "DBHandler", library_id: int, seq_request_id: int, indexed: bool, status: LibraryStatusEnum
) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    cloned_library = self.create_library(
        name=library.name,
        sample_name=library.sample_name,
        library_type=library.type,
        seq_request_id=seq_request_id,
        owner_id=library.owner_id,
        genome_ref=library.genome_ref,
        assay_type=library.assay_type,
        mux_type=library.mux_type,
        properties=library.properties,
        index_type=library.index_type,
        nuclei_isolation=library.nuclei_isolation,
        original_library_id=library.original_library_id if library.original_library_id is not None else library.id,
        status=status
    )

    for sample_link in library.sample_links:
        self.link_sample_library(
            sample_id=sample_link.sample_id,
            library_id=cloned_library.id,
            mux=sample_link.mux if sample_link.mux is not None else None,
        )

    for feature in library.features:
        self.link_feature_library(
            feature_id=feature.id,
            library_id=cloned_library.id
        )

    if indexed:
        for index in library.indices:
            self.add_library_index(
                library_id=cloned_library.id,
                index_kit_i7_id=index.index_kit_i7_id,
                name_i7=index.name_i7,
                sequence_i7=index.sequence_i7,
                index_kit_i5_id=index.index_kit_i5_id,
                name_i5=index.name_i5,
                sequence_i5=index.sequence_i5,
            )

    if not persist_session:
        self.close_session()

    return cloned_library