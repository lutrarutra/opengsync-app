import math
import time
from typing import Optional

from sqlmodel import func, text, or_

from ... import models, PAGE_LIMIT
from ...categories import LibraryType
from .. import exceptions


def create_library(
    self,
    library_type: LibraryType,
    owner_id: int,
    sample_id: Optional[int] = None,
    name: Optional[str] = None,
    kit: str = "custom",
    volume: Optional[int] = None,
    dna_concentration: Optional[float] = None,
    total_size: Optional[int] = None,
    index_1_sequence: Optional[str] = None,
    index_2_sequence: Optional[str] = None,
    index_3_sequence: Optional[str] = None,
    index_4_sequence: Optional[str] = None,
    index_1_adapter: Optional[str] = None,
    index_2_adapter: Optional[str] = None,
    index_3_adapter: Optional[str] = None,
    index_4_adapter: Optional[str] = None,
    commit: bool = True
) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.User, owner_id) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")
    
    if sample_id is not None:
        if (sample := self._session.get(models.Sample, sample_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
        name = sample.name
        sample.num_libraries += 1
        self._session.add(sample)

    if name is None:
        raise exceptions.InvalidValue("Name cannot be None")

    library = models.Library(
        sample_id=sample_id,
        name=name,
        type_id=library_type.value.id,
        owner_id=owner_id,
        kit=kit,
        volume=volume,
        dna_concentration=dna_concentration,
        total_size=total_size,
        index_1_sequence=index_1_sequence,
        index_2_sequence=index_2_sequence,
        index_3_sequence=index_3_sequence,
        index_4_sequence=index_4_sequence,
        index_1_adapter=index_1_adapter,
        index_2_adapter=index_2_adapter,
        index_3_adapter=index_3_adapter,
        index_4_adapter=index_4_adapter,
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
    sort_by: Optional[str] = None, descending: bool = False,
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
        query = query.join(
            models.SeqRequestLibraryLink,
            models.SeqRequestLibraryLink.library_id == models.Library.id,
            isouter=True
        ).where(
            models.SeqRequestLibraryLink.seq_request_id == seq_request_id
        )

    if sample_id is not None:
        query = query.where(
            models.Library.sample_id == sample_id
        )

    if experiment_id is not None:
        query = query.join(
            models.LibraryPoolLink,
            models.LibraryPoolLink.library_id == models.Library.id,
            isouter=True
        ).join(
            models.ExperimentPoolLink,
            models.ExperimentPoolLink.pool_id == models.LibraryPoolLink.pool_id,
            isouter=True
        ).where(
            models.ExperimentPoolLink.experiment_id == experiment_id
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


def get_num_libraries(self, user_id: Optional[int] = None) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Library)
    if user_id is not None:
        query = query.where(
            models.Library.owner_id == user_id
        )

    res = query.count()

    if not persist_session:
        self.close_session()
    return res


def delete_library(
    self, library_id: int,
    commit: bool = True
):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    library.owner.num_libraries -= 1
    for sample in library.samples:
        sample.num_libraries -= 1
        self._session.add(sample)
    for pool in library.pools:
        pool.num_libraries -= 1
        self._session.add(pool)
    for seq_request in library.seq_requests:
        seq_request.num_libraries -= 1
        self._session.add(seq_request)
        
    self._session.delete(library)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def update_library(
    self, library_id: int,
    library_type: Optional[LibraryType] = None,
    index_kit_id: Optional[int] = None,
    index_1_sequence: Optional[str] = None,
    index_2_sequence: Optional[str] = None,
    index_3_sequence: Optional[str] = None,
    index_4_sequence: Optional[str] = None,
    index_1_adapter: Optional[str] = None,
    index_2_adapter: Optional[str] = None,
    index_3_adapter: Optional[str] = None,
    index_4_adapter: Optional[str] = None,
    commit: bool = True
) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    library = self._session.get(models.Library, library_id)
    if not library:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    if library_type is not None:
        library.library_type_id = library_type.value.id
    if index_kit_id is not None:
        if self._session.get(models.IndexKit, index_kit_id) is None:
            raise exceptions.ElementDoesNotExist(f"index_kit with id {index_kit_id} does not exist")
        library.index_kit_id = index_kit_id
    else:
        library.index_kit_id = None

    if index_1_sequence is not None:
        library.index_1_sequence = index_1_sequence
    if index_2_sequence is not None:
        library.index_2_sequence = index_2_sequence
    if index_3_sequence is not None:
        library.index_3_sequence = index_3_sequence
    if index_4_sequence is not None:
        library.index_4_sequence = index_4_sequence
        
    if index_1_adapter is not None:
        library.index_1_adapter = index_1_adapter
    if index_2_adapter is not None:
        library.index_2_adapter = index_2_adapter
    if index_3_adapter is not None:
        library.index_3_adapter = index_3_adapter
    if index_4_adapter is not None:
        library.index_4_adapter = index_4_adapter

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
        query = query.join(
            models.SeqRequestLibraryLink,
            models.SeqRequestLibraryLink.library_id == models.Library.id,
            isouter=True
        ).where(
            models.SeqRequestLibraryLink.seq_request_id == seq_request_id
        )

    if sample_id is not None:
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
            models.LibraryPoolLink,
            models.LibraryPoolLink.library_id == models.Library.id,
            isouter=True
        ).join(
            models.ExperimentPoolLink,
            models.ExperimentPoolLink.pool_id == models.LibraryPoolLink.pool_id,
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