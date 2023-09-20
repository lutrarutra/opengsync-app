from typing import Optional, Union

import pandas as pd

from ... import models, logger
from .. import exceptions
from ...tools import SearchResult
from ...categories import LibraryType
from ._link_methods import link_index_kit_library_type


def create_index_kit(
    self,
    name: str,
    allowed_library_types: list[LibraryType]
) -> models.index_kit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.index_kit).where(models.index_kit.name == name).first():
        raise exceptions.NotUniqueValue(f"index_kit with name '{name}', already exists.")

    seq_kit = models.index_kit(
        name=name
    )
    self._session.add(seq_kit)
    self._session.commit()
    self._session.refresh(seq_kit)

    for library_type in allowed_library_types:
        link_index_kit_library_type(self, seq_kit.id, library_type.value.id)

    if not persist_session:
        self.close_session()
    return seq_kit


def get_index_kit(self, id: int) -> models.index_kit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.index_kit, id)
    library_types_ids = self._session.query(models.index_kitLibraryType.library_type_id).where(
        models.index_kitLibraryType.index_kit_id == id
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


def get_index_kit_by_name(self, name: str) -> models.index_kit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.index_kit).where(models.index_kit.name == name).first()
    if not persist_session:
        self.close_session()
    return res


def get_num_index_kits(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.IndexKit).count()
    if not persist_session:
        self.close_session()
    return res


def query_index_kit(
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
        index_kit
    JOIN
        index_kitlibrarytype
    ON
        index_kit.id = index_kitlibrarytype.index_kit_id
    """
    if library_type is not None:
        q += """WHERE
        index_kitlibrarytype.library_type_id = %(library_type_id)s"""

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
