import math
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.sql.operators import or_, and_  # noqa F401

from ... import models, PAGE_LIMIT
from ...categories import LibraryTypeEnum, LibraryStatus, LibraryStatusEnum, GenomeRefEnum, PoolStatus
from .. import exceptions


def create_library(
    self,
    name: str,
    sample_name: str,
    library_type: LibraryTypeEnum,
    owner_id: int,
    seq_request_id: int,
    genome_ref: Optional[GenomeRefEnum] = None,
    index_kit_id: Optional[int] = None,
    pool_id: Optional[int] = None,
    visium_annotation_id: Optional[int] = None,
    seq_depth_requested: Optional[float] = None,
    commit: bool = True
) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self._session.get(models.User, owner_id) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")
    
    if index_kit_id is not None:
        if (_ := self._session.get(models.IndexKit, index_kit_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Index kit with id {index_kit_id} does not exist")
    
    if seq_request_id is not None:
        if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Seq request with id {seq_request_id} does not exist")
        seq_request.num_libraries += 1
        self._session.add(seq_request)

    if visium_annotation_id is not None:
        if (_ := self._session.get(models.VisiumAnnotation, visium_annotation_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Visium annotation with id {visium_annotation_id} does not exist")
        
    if pool_id is not None:
        if (pool := self._session.get(models.Pool, pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
        pool.num_libraries += 1
        self._session.add(pool)
        library_status_id = LibraryStatus.POOLED.id
    else:
        library_status_id = LibraryStatus.DRAFT.id

    library = models.Library(
        name=name.strip(),
        sample_name=sample_name,
        seq_request_id=seq_request_id,
        genome_ref_id=genome_ref.id if genome_ref is not None else None,
        type_id=library_type.id,
        owner_id=owner_id,
        index_kit_id=index_kit_id,
        pool_id=pool_id,
        status_id=library_status_id,
        visium_annotation_id=visium_annotation_id,
        seq_depth_requested=seq_depth_requested
    )

    self._session.add(library)

    if commit:
        self._session.commit()
        self._session.refresh(library)

    if not persist_session:
        self.close_session()

    return library


def get_library(self, library_id: int) -> Optional[models.Library]:
    if not (persist_session := self._session is not None):
        self.open_session()

    library = self._session.get(models.Library, library_id)
    
    if not persist_session:
        self.close_session()
    return library


def get_libraries(
    self,
    user_id: Optional[int] = None, sample_id: Optional[int] = None,
    experiment_id: Optional[int] = None, seq_request_id: Optional[int] = None,
    pool_id: Optional[int] = None, lab_prep_id: Optional[int] = None,
    type_in: Optional[list[LibraryTypeEnum]] = None,
    status_in: Optional[list[LibraryStatusEnum]] = None,
    pooled: Optional[bool] = None, status: Optional[LibraryStatusEnum] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
) -> tuple[list[models.Library], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.Library)
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
        query = query.join(
            models.LibraryLabPrepLink,
            models.LibraryLabPrepLink.library_id == models.Library.id
        ).where(
            models.LibraryLabPrepLink.lab_prep_id == lab_prep_id
        )

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


def delete_library(self, library_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()

    library: models.Library
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    for link in library.sample_links:
        link.sample.num_libraries -= 1
            
        if link.sample.num_libraries == 0:
            self.delete_sample(link.sample_id)

    if library.pool is not None:
        library.pool.num_libraries -= 1
        if library.pool.num_libraries == 0:
            self.delete_pool(library.pool_id)

    orphan_features = set()
    for feature in library.features:
        if feature.feature_kit_id is None:
            if self._session.query(models.LibraryFeatureLink).where(
                models.LibraryFeatureLink.feature_id == feature.id
            ).count() == 1:
                orphan_features.add(feature)

    library.seq_request.num_libraries -= 1
    self._session.delete(library)
    self._session.commit()

    for feature in orphan_features:
        self._session.delete(feature)

    if not persist_session:
        self.close_session()


def update_library(self, library: models.Library) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()
    
    self._session.add(library)
    self._session.commit()
    self._session.refresh(library)

    if not persist_session:
        self.close_session()
    return library


def query_libraries(
    self, word: str,
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

    query = self._session.query(models.Library)

    if user_id is not None:
        if self._session.get(models.User, user_id) is None:
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

    query = query.order_by(
        sa.func.similarity(models.Library.name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    libraries = query.all()

    if not persist_session:
        self.close_session()

    return libraries


def pool_library(self, library_id: int, pool_id: int) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    library: models.Library
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    if library.pool_id is not None:
        raise exceptions.LinkAlreadyExists(f"Library with id {library_id} is already pooled")

    pool: models.Pool
    if (pool := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
        
    library.pool_id = pool_id
    if library.is_indexed():
        library.status_id = LibraryStatus.POOLED.id
    else:
        library.status_id = LibraryStatus.PREPARING.id
    self._session.add(library)

    pool.num_libraries += 1
    self._session.add(pool)

    self._session.commit()

    if not persist_session:
        self.close_session()

    return library


def set_library_seq_quality(
    self, library_id: Optional[int], experiment_id: int, lane: int,
    num_lane_reads: int, num_library_reads: int,
    mean_quality_pf_r1: float, q30_perc_r1: float,
    mean_quality_pf_i1: float, q30_perc_i1: float,
    mean_quality_pf_r2: Optional[float], q30_perc_r2: Optional[float],
    mean_quality_pf_i2: Optional[float], q30_perc_i2: Optional[float],
) -> models.SeqQuality:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    if library_id is not None:
        if (library := self._session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
        
        library.status_id = LibraryStatus.SEQUENCED.id
        library.pool.status_id = PoolStatus.SEQUENCED.id
        self._session.add(library)
        
    if (quality := self._session.query(models.SeqQuality).where(
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

    self._session.add(quality)
    self._session.commit()
    self._session.refresh(quality)

    if not persist_session:
        self.close_session()

    return quality


def add_library_index(
    self, library_id: int, name_i7: Optional[str], sequence_i7: Optional[str], name_i5: Optional[str], sequence_i5: Optional[str]
) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    library.indices.append(models.LibraryIndex(
        library_id=library_id,
        name_i7=name_i7,
        sequence_i7=sequence_i7,
        name_i5=name_i5,
        sequence_i5=sequence_i5,
    ))

    self._session.add(library)
    self._session.commit()
    self._session.refresh(library)

    if not persist_session:
        self.close_session()

    return library


def remove_library_indices(self, library_id: int) -> models.Library:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    for index in library.indices:
        self._session.delete(index)

    self._session.commit()
    self._session.refresh(library)

    if not persist_session:
        self.close_session()

    return library