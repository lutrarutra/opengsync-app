from typing import Optional

import pandas as pd
from sqlmodel import func

from ... import models
from ...categories import LibraryType, UserResourceRelation
from .. import exceptions
from ...tools import SearchResult


def create_library(
    self, name: str,
    library_type: LibraryType,
    index_kit_id: Optional[int],
    owner_id: int,
) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if index_kit_id is not None:
        if (_ := self._session.get(models.IndexKit, index_kit_id)) is None:
            raise exceptions.ElementDoesNotExist(f"index_kit with id {index_kit_id} does not exist")

    if self._session.get(models.User, owner_id) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")

    library = models.Library(
        name=name,
        library_type_id=library_type.value.id,
        index_kit_id=index_kit_id,
        owner_id=owner_id
    )
    self._session.add(library)
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
    user_id: Optional[int] = None, seq_request_id: Optional[int] = None,
    sort_by: Optional[str] = None, reversed: bool = False,
    limit: Optional[int] = 20, offset: Optional[int] = None,
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
            models.Library.seq_requests
        ).where(
            models.LibrarySeqRequestLink.seq_request_id == seq_request_id
        )

    if sort_by is not None:
        attr = getattr(models.Library, sort_by)
        if reversed:
            attr = attr.desc()
        query = query.order_by(attr)

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    n_pages: int = query.count() // limit if limit is not None else 1
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
) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    library = self._session.get(models.Library, library_id)
    if not library:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    self._session.delete(library)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def update_library(
    self, library_id: int,
    name: Optional[str] = None,
    library_type: Optional[LibraryType] = None,
    index_kit_id: Optional[int] = None,
    commit: bool = True
) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    library = self._session.get(models.Library, library_id)
    if not library:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    if name is not None:
        _lib = self._session.query(models.Library).where(
            models.Library.name == name
        ).first()
        if _lib is not None and _lib.id != library_id:
            raise exceptions.NotUniqueValue(f"Library with name {name} already exists")

    if name is not None:
        library.name = name
    if library_type is not None:
        library.library_type_id = library_type.value.id
    if index_kit_id is not None:
        if self._session.get(models.IndexKit, index_kit_id) is None:
            raise exceptions.ElementDoesNotExist(f"index_kit with id {index_kit_id} does not exist")
        library.index_kit_id = index_kit_id
    else:
        library.index_kit_id = None

    self._session.add(library)
    if commit:
        self._session.commit()
        self._session.refresh(library)

    if not persist_session:
        self.close_session()
    return library


def query_libraries(
    self, word: str,
    user_id: Optional[int] = None,
    limit: Optional[int] = 20,
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

    query = query.order_by(
        func.similarity(models.Library.name, word)
    )

    if limit is not None:
        query = query.limit(limit)

    libraries = query.all()

    if not persist_session:
        self.close_session()

    return libraries


def create_library_type(
    self, type: LibraryType
) -> models.LibraryTypeId:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.LibraryTypeId).where(
        models.LibraryTypeId.id == type.value.id
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"LibraryType with id {type.value.id} already exists")

    lib_type = models.LibraryTypeId(
        id=type.value.id
    )

    self._session.add(lib_type)
    self._session.commit()

    if not persist_session:
        self.close_session()

    return lib_type