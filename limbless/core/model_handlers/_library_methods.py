from typing import Optional

import pandas as pd

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
            raise exceptions.ElementDoesNotExist(f"IndexKit with id {index_kit_id} does not exist")

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
    self, limit: Optional[int] = 20, offset: Optional[int] = None,
    user_id: Optional[int] = None
) -> list[models.Library]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Library).order_by(models.Library.id.desc())
    if user_id is not None:
        query = query.where(
            models.Library.owner_id == user_id
        )

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    libraries = query.all()

    for library in libraries:
        library._num_samples = len(library.samples)

    if not persist_session:
        self.close_session()

    return libraries


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
            raise exceptions.ElementDoesNotExist(f"IndexKit with id {index_kit_id} does not exist")
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
) -> list[SearchResult]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    q = """
    SELECT
        id, name,
        similarity(lower(library.name), lower(%(word)s)) as sml
    FROM
        library
    """
    if user_id is not None:
        if self._session.get(models.User, user_id) is None:
            raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")
        q += """
            JOIN
                libraryuserlink
            ON
                library.id = libraryuserlink.library_id
            WHERE
                libraryuserlink.user_id = %(user_id)s
            """
    q += """
        ORDER BY
            sml DESC
    """
    if limit is not None:
        q += """
            LIMIT
                %(limit)s;
            """
    res = pd.read_sql(q, self._engine, params={"word": word, "user_id": user_id, "limit": limit})
    res = [
        SearchResult(
            value=row["id"],
            name=row["name"],
        ) for _, row in res.iterrows()
    ]

    if not persist_session:
        self.close_session()

    return res