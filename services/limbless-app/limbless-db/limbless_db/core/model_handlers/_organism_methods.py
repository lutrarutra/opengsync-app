from typing import Optional

from sqlmodel import func

from ... import models, PAGE_LIMIT
from .. import exceptions
from ...core.categories import OrganismCategory


def create_organism(
    self,
    tax_id: int,
    scientific_name: str,
    category: OrganismCategory,
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
        category=category.id,
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
    self, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None
) -> list[models.Organism]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Organism)
    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

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


def query_organisms(self, word: str, limit: Optional[int] = PAGE_LIMIT) -> list[models.Organism]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Organism)

    query = query.order_by(
        func.greatest(
            func.similarity(models.Organism.scientific_name, word),
            func.similarity(models.Organism.common_name, word),
        ).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    organisms = query.all()

    if not persist_session:
        self.close_session()

    return organisms
