from typing import Optional

from sqlmodel import and_
import pandas as pd

from ... import models, logger
from .. import exceptions
from ...tools import SearchResult


def create_seqindex(
    self,
    sequence: str,
    adapter: str,
    type: str,
    index_kit_id: int,
    commit: bool = True
) -> models.SeqIndex:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (index_kit := self._session.get(models.IndexKit, index_kit_id)) is None:
        raise exceptions.ElementDoesNotExist(f"IndexKit with id '{index_kit_id}', not found.")

    seq_index = models.SeqIndex(
        sequence=sequence,
        adapter=adapter,
        type=type,
        index_kit_id=index_kit.id
    )

    self._session.add(seq_index)
    if commit:
        self._session.commit()
        self._session.refresh(seq_index)

    if not persist_session:
        self.close_session()
    return seq_index


def get_seqindex(self, id: int) -> models.SeqIndex:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqIndex).where(models.SeqIndex.id == id).first()
    if not persist_session:
        self.close_session()
    return res


def get_seqindices_by_adapter(self, adapter: str) -> list[models.SeqIndex]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqIndex).where(models.SeqIndex.adapter == adapter).all()
    if not persist_session:
        self.close_session()
    return res


def get_num_seqindices(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqIndex).count()
    if not persist_session:
        self.close_session()
    return res


def query_adapters(
    self, query: str, index_kit_id: Optional[int] = None,
    limit: Optional[int] = 10,
) -> list[SearchResult]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    params: dict[str, str | int] = {"word": query}    

    q = """
SELECT seqindex.adapter, seqindex.id, seqindex.sequence, seqindex.type, sml
	FROM (
		SELECT
			DISTINCT adapter,
			similarity(lower(adapter), lower(%(word)s)) AS sml
		FROM
			seqindex"""
    if index_kit_id is not None:
        q += """
    WHERE
        index_kit_id = %(index_kit_id)s"""
        params["index_kit_id"] = index_kit_id
    q += """
    ORDER BY
        sml DESC"""
    
    if limit is not None:
        q += """
    LIMIT %(limit)s"""
        params["limit"] = limit

    q += """
    ) AS other
INNER JOIN
    seqindex
ON
    other.adapter = seqindex.adapter
ORDER BY sml DESC;"""
    res = pd.read_sql(q, self._engine, params=params)

    adapters = {}
    for _, row in res.iterrows():
        if row["adapter"] not in adapters.keys():
            adapters[row["adapter"]] = []

        adapters[row["adapter"]].append((row["sequence"], row["type"]))

    res = []
    for adapter, sequences in adapters.items():
        res.append(SearchResult(
            adapter, adapter,
            description=", ".join([f"{s[0]} [{s[1]}]" for s in sequences])
        ))

    if not persist_session:
        self.close_session()
    return res


def get_adapters_from_kit(
    self, index_kit_id: int, limit: Optional[int] = None
) -> list[SearchResult]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.SeqIndex.adapter).where(
        models.SeqIndex.index_kit_id == index_kit_id
    ).distinct()

    if limit is not None:
        res = res.limit(limit)

    res = res.all()

    res = [SearchResult(a[0], a[0]) for a in res]

    if not persist_session:
        self.close_session()
    return res
