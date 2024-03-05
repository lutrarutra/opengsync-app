import math
from typing import Optional

from sqlmodel import func, text
from sqlalchemy.sql.operators import or_, and_

from ... import models, PAGE_LIMIT
from ...core.categories import LibraryType, LibraryStatus
from .. import exceptions


def create_library(
    self,
    library_type: LibraryType,
    owner_id: int,
    name: str,
    seq_request_id: int,
    volume: Optional[int] = None,
    index_kit_id: Optional[int] = None,
    dna_concentration: Optional[float] = None,
    total_size: Optional[int] = None,
    pool_id: Optional[int] = None,
    index_1_sequence: Optional[str] = None,
    index_2_sequence: Optional[str] = None,
    index_3_sequence: Optional[str] = None,
    index_4_sequence: Optional[str] = None,
    adapter: Optional[str] = None,
    visium_annotation_id: Optional[int] = None,
    commit: bool = True
) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
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
        library_status_id = LibraryStatus.POOLED.id
    else:
        library_status_id = LibraryStatus.DRAFT.id

    library = models.Library(
        name=name,
        seq_request_id=seq_request_id,
        type_id=library_type.id,
        owner_id=owner_id,
        volume=volume,
        index_kit_id=index_kit_id,
        pool_id=pool_id,
        dna_concentration=dna_concentration,
        total_size=total_size,
        index_1_sequence=index_1_sequence,
        index_2_sequence=index_2_sequence,
        index_3_sequence=index_3_sequence,
        index_4_sequence=index_4_sequence,
        adapter=adapter,
        status_id=library_status_id,
        visium_annotation_id=visium_annotation_id
    )
    self._session.add(library)

    if commit:
        self._session.commit()
        self._session.refresh(library)

    if not persist_session:
        self.close_session()

    return library


def get_library(self, library_id: int) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    library = self._session.get(models.Library, library_id)
    if not persist_session:
        self.close_session()
    return library


def get_libraries(
    self,
    user_id: Optional[int] = None, sample_id: Optional[int] = None,
    experiment_id: Optional[int] = None, seq_request_id: Optional[int] = None,
    pool_id: Optional[int] = None, sort_by: Optional[str] = None, descending: bool = False,
    pooled: Optional[bool] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
) -> tuple[list[models.Library], int]:
    persist_session = self._session is not None
    if not self._session:
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
            models.SeqRequestExperimentLink,
            models.SeqRequestExperimentLink.seq_request_id == models.Library.seq_request_id,
            isouter=True
        ).where(
            models.SeqRequestExperimentLink.experiment_id == experiment_id
        ).distinct()

    if pooled is not None:
        if pooled:
            query = query.where(
                models.Library.pool_id != None # noqa
            )
        else:
            query = query.where(
                models.Library.pool_id == None # noqa
            )

    if pool_id is not None:
        query = query.where(
            models.Library.pool_id == pool_id
        )

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if sort_by is not None:
        if sort_by == "sample_name":
            if descending:
                attr = text("sample_1_name DESC")
            else:
                attr = text("sample_1_name")
        elif sort_by == "owner_id":
            if descending:
                attr = text("user_2_id DESC")
            else:
                attr = text("user_2_id")
        else:
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
    self, library_id: int,
    commit: bool = True
):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    for link in library.sample_links:
        link.sample.num_libraries -= 1
        self._session.add(link.sample)
        if link.cmo is not None:
            self._session.delete(link.cmo)
        self._session.delete(link)

    seq_request = library.seq_request
    seq_request.num_libraries -= 1
    self._session.add(seq_request)
        
    self._session.delete(library)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def update_library(
    self, library: models.Library,
    commit: bool = True
) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    self._session.add(library)

    if commit:
        self._session.commit()
        self._session.refresh(library)

    if not persist_session:
        self.close_session()
    return library


def query_libraries(
    self, word: str,
    user_id: Optional[int] = None, sample_id: Optional[int] = None,
    seq_request_id: Optional[int] = None, experiment_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT,
) -> list[models.Library]:

    persist_session = self._session is not None
    if not self._session:
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
        raise NotImplementedError()
        query = query.join(
            models.SampleLibraryLink,
            models.SampleLibraryLink.library_id == models.Library.id,
            isouter=True
        ).where(
            or_(
                models.SampleLibraryLink.sample_id == sample_id,
                models.Library.sample_id == sample_id
            )
        )

    if experiment_id is not None:
        query = query.join(
            models.ExperimentPoolLink,
            models.ExperimentPoolLink.pool_id == models.Library.pool_id,
            isouter=True
        ).where(
            models.ExperimentPoolLink.experiment_id == experiment_id
        )

    query = query.order_by(
        func.similarity(models.Library.name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    libraries = query.all()

    if not persist_session:
        self.close_session()

    return libraries


def link_library_pool(self, library_id: int, pool_id: int, commit: bool = True):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    if (pool := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

    if library.pool_id is None:
        pool.num_libraries += 1
        self._session.add(pool)
        
    library.pool_id = pool_id
    library.status_id = LibraryStatus.POOLED.id
    self._session.add(library)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def set_library_seq_quality(
    self, library_id: int, experiment_id: int, lane: int,
    num_lane_reads: int, num_total_reads: int,
    mean_quality_pf_r1: float, q30_perc_r1: float,
    mean_quality_pf_i1: float, q30_perc_i1: float,
    mean_quality_pf_r2: Optional[float], q30_perc_r2: Optional[float],
    mean_quality_pf_i2: Optional[float], q30_perc_i2: Optional[float]
) -> models.SeqQuality:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
        
    if (quality := self._session.query(models.SeqQuality).where(
        models.SeqQuality.library_id == library_id,
        models.SeqQuality.experiment_id == experiment_id,
        models.SeqQuality.lane == lane,
    ).first()) is not None:
        quality.num_lane_reads = num_lane_reads
        quality.num_total_reads = num_total_reads
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
            num_lane_reads=num_lane_reads, num_total_reads=num_total_reads,
            mean_quality_pf_r1=mean_quality_pf_r1, q30_perc_r1=q30_perc_r1,
            mean_quality_pf_i1=mean_quality_pf_i1, q30_perc_i1=q30_perc_i1,
            mean_quality_pf_r2=mean_quality_pf_r2, q30_perc_r2=q30_perc_r2,
            mean_quality_pf_i2=mean_quality_pf_i2, q30_perc_i2=q30_perc_i2
        )

    self._session.add(quality)
    self._session.commit()
    self._session.refresh(quality)

    if not persist_session:
        self.close_session()

    return quality