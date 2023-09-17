from typing import Optional, Union

import pandas as pd

from ... import models, logger
from .. import exceptions
from ...tools import SearchResult
from ...categories import LibraryType
from ._link_methods import link_indexkit_library_type


def create_indexkit(
    self,
    name: str,
    allowed_library_types: list[LibraryType]
) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.IndexKit).where(models.IndexKit.name == name).first():
        raise exceptions.ElementAlreadyExists(f"IndexKit with name '{name}', already exists.")

    seq_kit = models.IndexKit(
        name=name
    )
    self._session.add(seq_kit)
    self._session.commit()
    self._session.refresh(seq_kit)

    for library_type in allowed_library_types:
        link_indexkit_library_type(self, seq_kit.id, library_type.value.id)

    if not persist_session:
        self.close_session()
    return seq_kit


def get_indexkit(self, id: int) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.IndexKit, id)
    library_types_ids = self._session.query(models.IndexKitLibraryType.library_type_id).where(
        models.IndexKitLibraryType.index_kit_id == id
    ).all()

    library_types_ids, *_ = zip(*library_types_ids)

    res._library_types = []
    for library_type_id in library_types_ids:
        logger.debug(library_type_id)
        logger.debug(type(library_type_id))
        res._library_types.append(LibraryType.get(library_type_id))
    
    if not persist_session:
        self.close_session()

    return res


def get_indexkit_by_name(self, name: str) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.IndexKit).where(models.IndexKit.name == name).first()
    if not persist_session:
        self.close_session()
    return res


def query_indexkit(
    self, query: str, library_type: Optional[LibraryType] = None, limit: Optional[int] = 20
) -> list[SearchResult]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    q = """
    SELECT
        *,
        similarity(lower(name), lower(%(word)s)) as sml
    FROM
        indexkit
    JOIN
        indexkitlibrarytype
    ON
        indexkit.id = indexkitlibrarytype.index_kit_id
    """
    if library_type is not None:
        q += """WHERE
        indexkitlibrarytype.library_type_id = %(library_type_id)s"""
        
    q += """
    ORDER BY
        sml DESC
    LIMIT %(limit)s;
    """

    res = pd.read_sql(
        q, self._engine,
        params={
            "word": query,
            "limit": str(limit),
        } | ({"library_type_id": library_type.value.id} if library_type is not None else {})
    )
    res = [SearchResult(int(row["id"]), row["name"]) for _, row in res.iterrows()]

    if not persist_session:
        self.close_session()
    return res
