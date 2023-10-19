from typing import Optional

import pandas as pd

from ... import models
from .. import exceptions
from ... import categories
from ...tools import SearchResult


def create_organism(
    self,
    tax_id: int,
    scientific_name: str,
    category: categories.OrganismCategory,
    common_name: Optional[str] = None,
    commit: bool = True
) -> models.Organism:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Organism, tax_id):
        raise exceptions.NotUniqueValue(f"Organism with tax_id '{tax_id}', already exists.")

    organism = models.Organism(
        tax_id=tax_id,
        scientific_name=scientific_name,
        category=category.value.id,
        common_name=common_name
    )

    self._session.add(organism)
    if commit:
        self._session.commit()
        self._session.refresh(organism)

    if not persist_session:
        self.close_session()
    return organism


def get_organism(self, tax_id: int) -> models.Organism:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.Organism, tax_id)
    if not persist_session:
        self.close_session()
    return res


def get_num_organisms(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Organism).count()
    if not persist_session:
        self.close_session()
    return res


def get_organisms(
    self, limit: Optional[int] = 20, offset: Optional[int] = None
) -> list[models.Organism]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Organism)
    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        organisms = query.limit(limit).all()
    else:
        organisms = query.all()

    if not persist_session:
        self.close_session()
    return organisms


def get_organisms_by_name(self, name: str) -> list[models.Organism]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    organism = self._session.query(models.Organism).filter_by(name=name).all()
    if not persist_session:
        self.close_session()
    return organism


def query_organisms(self, word: str, limit: Optional[int] = 20) -> list[SearchResult]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    q = f"""
    SELECT
        *,
        greatest(similarity(common_name, %(word)s), similarity(scientific_name, %(word)s)) AS score
    FROM
        organism
    WHERE
        common_name %% %(word)s
    OR
        scientific_name %% %(word)s
    ORDER BY
        score DESC
    LIMIT {limit};
    """
    res = pd.read_sql(q, self._engine, params={"word": word})
    res = [
        SearchResult(
            value=int(row["tax_id"]),
            name=f"{row['scientific_name']} [{row['tax_id']}] {'(' + row['common_name'] + ')' if row['common_name'] else ''}"
        ) for _, row in res.iterrows()
    ]

    if not persist_session:
        self.close_session()
    return res
