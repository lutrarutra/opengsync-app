import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.sql.operators import or_, and_  # noqa F401

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from ...categories import LibraryTypeEnum, LibraryStatus, LibraryStatusEnum, GenomeRefEnum, PoolStatus, AccessType, AccessTypeEnum
from .. import exceptions


def create_library(
    self: "DBHandler",
    name: str,
    sample_name: str,
    library_type: LibraryTypeEnum,
    owner_id: int,
    seq_request_id: int,
    genome_ref: Optional[GenomeRefEnum] = None,
    pool_id: Optional[int] = None,
    visium_annotation_id: Optional[int] = None,
    seq_depth_requested: Optional[float] = None,
    commit: bool = True
) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self.session.get(models.User, owner_id) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")
    
    if seq_request_id is not None:
        if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Seq request with id {seq_request_id} does not exist")
        seq_request.num_libraries += 1
        self.session.add(seq_request)

    if visium_annotation_id is not None:
        if (_ := self.session.get(models.VisiumAnnotation, visium_annotation_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Visium annotation with id {visium_annotation_id} does not exist")
        
    if pool_id is not None:
        if (pool := self.session.get(models.Pool, pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
        pool.num_libraries += 1
        self.session.add(pool)
        library_status = LibraryStatus.POOLED
    else:
        library_status = LibraryStatus.DRAFT

    library = models.Library(
        name=name.strip(),
        sample_name=sample_name,
        seq_request_id=seq_request_id,
        genome_ref_id=genome_ref.id if genome_ref is not None else None,
        type_id=library_type.id,
        owner_id=owner_id,
        pool_id=pool_id,
        status_id=library_status.id,
        visium_annotation_id=visium_annotation_id,
        seq_depth_requested=seq_depth_requested
    )

    self.session.add(library)

    if commit:
        self.session.commit()
        self.session.refresh(library)

    if not persist_session:
        self.close_session()

    return library


def get_library(self: "DBHandler", library_id: int) -> Optional[models.Library]:
    if not (persist_session := self._session is not None):
        self.open_session()

    library = self.session.get(models.Library, library_id)
    
    if not persist_session:
        self.close_session()
    return library


def get_libraries(
    self: "DBHandler",
    user_id: Optional[int] = None, sample_id: Optional[int] = None,
    experiment_id: Optional[int] = None, seq_request_id: Optional[int] = None,
    pool_id: Optional[int] = None, lab_prep_id: Optional[int] = None,
    in_lab_prep: Optional[bool] = None,
    type_in: Optional[list[LibraryTypeEnum]] = None,
    status_in: Optional[list[LibraryStatusEnum]] = None,
    pooled: Optional[bool] = None, status: Optional[LibraryStatusEnum] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
) -> tuple[list[models.Library], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Library)
    if user_id is not None:
        query = query.where(
            models.Library.owner_id == user_id
        )

    if seq_request_id is not None:
        query = query.where(
            models.Library.seq_request_id == seq_request_id
        )

    if sample_id is not None:
        query = query.join(
            models.SampleLibraryLink,
            and_(
                models.SampleLibraryLink.library_id == models.Library.id,
                models.SampleLibraryLink.sample_id == sample_id
            )
        )

    if experiment_id is not None:
        query = query.join(
            models.Pool,
            models.Pool.id == models.Library.pool_id,
        ).join(
            models.ExperimentPoolLink,
            models.ExperimentPoolLink.pool_id == models.Pool.id,
        ).where(
            models.ExperimentPoolLink.experiment_id == experiment_id
        )

    if pooled is not None:
        if pooled:
            query = query.where(
                models.Library.pool_id != None # noqa
            )
        else:
            query = query.where(
                models.Library.pool_id == None # noqa
            )

    if status is not None:
        query = query.where(
            models.Library.status_id == status.id
        )

    if pool_id is not None:
        query = query.where(
            models.Library.pool_id == pool_id
        )

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
    
    libraries = query.all()

    if not persist_session:
        self.close_session()

    return libraries, n_pages


def delete_library(self: "DBHandler", library_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    for link in library.sample_links:
        link.sample.num_libraries -= 1
            
        if link.sample.num_libraries == 0:
            self.delete_sample(link.sample_id)

    if library.pool_id is not None and library.pool is not None:
        library.pool.num_libraries -= 1
        if library.pool.num_libraries == 0:
            self.delete_pool(library.pool_id)

    orphan_features = set()
    for feature in library.features:
        if feature.feature_kit_id is None:
            if self.session.query(models.LibraryFeatureLink).where(
                models.LibraryFeatureLink.feature_id == feature.id
            ).count() == 1:
                orphan_features.add(feature)

    library.seq_request.num_libraries -= 1
    self.session.delete(library)
    self.session.commit()

    for feature in orphan_features:
        self.session.delete(feature)

    if not persist_session:
        self.close_session()


def update_library(self: "DBHandler", library: models.Library) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()
    
    self.session.add(library)
    self.session.commit()
    self.session.refresh(library)

    if not persist_session:
        self.close_session()
    return library


def query_libraries(
    self: "DBHandler", name: Optional[str] = None, owner: Optional[str] = None,
    user_id: Optional[int] = None, sample_id: Optional[int] = None,
    seq_request_id: Optional[int] = None, experiment_id: Optional[int] = None,
    type_in: Optional[list[LibraryTypeEnum]] = None,
    status_in: Optional[list[LibraryStatusEnum]] = None,
    pooled: Optional[bool] = None,
    status: Optional[LibraryStatusEnum] = None, pool_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT,
) -> list[models.Library]:

    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Library)

    if user_id is not None:
        if self.session.get(models.User, user_id) is None:
            raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")
        query = query.where(
            models.Library.owner_id == user_id
        )

    if seq_request_id is not None:
        query = query.where(
            models.Library.seq_request_id == seq_request_id
        )

    if sample_id is not None:
        query = query.join(
            models.SampleLibraryLink,
            and_(
                models.SampleLibraryLink.library_id == models.Library.id,
                models.SampleLibraryLink.sample_id == sample_id
            )
        )

    if type_in is not None:
        query = query.where(
            models.Library.type_id.in_([t.id for t in type_in])
        )

    if status_in is not None:
        query = query.where(
            models.Library.status_id.in_([s.id for s in status_in])
        )

    if pool_id is not None:
        query = query.where(
            models.Library.pool_id == pool_id
        )

    if status is not None:
        query = query.where(
            models.Library.status_id == status.id
        )

    if pooled is not None:
        if pooled:
            query = query.where(
                models.Library.pool_id != None # noqa
            )
        else:
            query = query.where(
                models.Library.pool_id == None # noqa
            )

    if experiment_id is not None:
        query = query.join(
            models.Pool,
            models.Pool.id == models.Library.pool_id,
        ).join(
            models.ExperimentPoolLink,
            models.ExperimentPoolLink.pool_id == models.Pool.id,
        ).where(
            models.ExperimentPoolLink.experiment_id == experiment_id
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


def pool_library(self: "DBHandler", library_id: int, pool_id: int) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    if library.pool_id is not None:
        raise exceptions.LinkAlreadyExists(f"Library with id {library_id} is already pooled")

    if (pool := self.session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
        
    library.pool_id = pool_id
    if library.is_indexed():
        library.status = LibraryStatus.POOLED
    else:
        library.status = LibraryStatus.PREPARING
    self.session.add(library)

    pool.num_libraries += 1
    self.session.add(pool)

    self.session.commit()

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
    self.session.commit()
    self.session.refresh(quality)

    if not persist_session:
        self.close_session()

    return quality


def add_library_index(
    self: "DBHandler", library_id: int,
    index_kit_i7_id: Optional[int], name_i7: Optional[str], sequence_i7: Optional[str],
    index_kit_i5_id: Optional[int], name_i5: Optional[str], sequence_i5: Optional[str],
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
    self.session.commit()
    self.session.refresh(library)

    if not persist_session:
        self.close_session()

    return library


def remove_library_indices(self: "DBHandler", library_id: int) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    for index in library.indices:
        self.session.delete(index)

    self.session.commit()
    self.session.refresh(library)

    if not persist_session:
        self.close_session()

    return library


def get_user_library_access_type(
    self: "DBHandler", library_id: int, user_id: int
) -> Optional[AccessTypeEnum]:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    access_type: Optional[AccessTypeEnum] = None

    if library.owner_id == user_id:
        access_type = AccessType.OWNER
    elif library.seq_request.group_id is not None:
        if self.session.query(models.UserAffiliation).where(
            models.UserAffiliation.user_id == user_id,
            models.UserAffiliation.group_id == library.seq_request.group_id
        ).first() is not None:
            access_type = AccessType.EDIT

    if not persist_session:
        self.close_session()

    return access_type


def clone_library(self: "DBHandler", library_id: int, seq_request_id: int, indexed: bool) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    cloned_library = self.create_library(
        name=library.name, sample_name=library.sample_name,
        library_type=library.type, seq_request_id=seq_request_id,
        owner_id=library.owner_id, genome_ref=library.genome_ref,
        visium_annotation_id=library.visium_annotation_id,
    )

    for sample_link in library.sample_links:
        self.link_sample_library(
            sample_id=sample_link.sample_id,
            library_id=cloned_library.id,
            cmo_sequence=sample_link.cmo_sequence,
            cmo_read=sample_link.cmo_read,
            cmo_pattern=sample_link.cmo_pattern,
            flex_barcode=sample_link.flex_barcode
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