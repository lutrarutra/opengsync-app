from typing import Optional, Union

import pandas as pd

from ... import models, logger
from .. import exceptions
from ...tools import SearchResult


def create_indexkit(
    self,
    name: str,
    commit: bool = True
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
    if commit:
        self._session.commit()
        self._session.refresh(seq_kit)

    if not persist_session:
        self.close_session()
    return seq_kit


def get_indexkit(self, id: int) -> models.IndexKit:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.IndexKit).where(models.IndexKit.id == id).first()
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
    self, query: str, limit: Optional[int] = 20
) -> list[SearchResult]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    q = f"""
    SELECT
        *,
        similarity(lower(name), lower(%(word)s)) as sml
    FROM
        indexkit
    ORDER BY
        sml DESC
    LIMIT {limit};
    """
    res = pd.read_sql(q, self._engine, params={"word": query})
    res = [SearchResult(int(row["id"]), row["name"]) for _, row in res.iterrows()]

    if not persist_session:
        self.close_session()
    return res
