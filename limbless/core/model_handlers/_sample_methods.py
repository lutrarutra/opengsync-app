from typing import Optional, Union

from sqlalchemy.orm import selectinload
from sqlmodel import and_

from ... import models
from .. import exceptions
from ...tools import SearchResult

def create_sample(
        self, name: str,
        organism_tax_id: int,
        project_id: int,
        commit: bool = True
    ) -> models.Sample:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if not self._session.get(models.Project, project_id):
        raise exceptions.ElementDoesNotExist(f"Project with id '{project_id}', not found.")

    if (organism := self._session.get(models.Organism, organism_tax_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Organism with tax_id '{organism_tax_id}', not found.")

    sample = models.Sample(
        name=name,
        organism_id=organism.tax_id,
        project_id=project_id
    )

    self._session.add(sample)
    if commit:
        self._session.commit()
        self._session.refresh(sample)

    if not persist_session: self.close_session()
    return sample

def get_sample(self, sample_id: int) -> models.Sample:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.Sample, sample_id)

    if not persist_session: self.close_session()
    return res

def get_num_samples(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Sample).count()
    if not persist_session: self.close_session()
    return res
    
def get_samples(
        self, limit: Optional[int]=20, offset: Optional[int]=None
    ) -> list[models.Sample]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sample)
    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        samples = query.limit(limit)
    else:
        samples = query.all()
    
    if not persist_session: self.close_session()
    return samples

def get_sample_by_name(self, name: str) -> models.Sample:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sample = self._session.query(models.Sample).filter_by(name=name).first()
    if not persist_session: self.close_session()
    return sample

def update_sample(
        self, sample_id: int,
        name: Optional[str] = None,
        organism_tax_id: Optional[int] = None,
        commit: bool = True
    ) -> models.Sample:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sample = self._session.get(models.Sample, sample_id)
    if not sample:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    if organism_tax_id is not None:
        if (organism := self._session.get(models.Organism, organism_tax_id)) is not None:
            sample.organism_id = organism_tax_id
            sample.organism = organism
        else:
            raise exceptions.ElementDoesNotExist(f"Organism with id {organism_tax_id} does not exist")

    if name is not None: sample.name = name

    if commit:
        self._session.commit()
        self._session.refresh(sample)

    if not persist_session: self.close_session()
    return sample

def delete_sample(
        self, sample_id: int,
        commit: bool = True
    ) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sample = self._session.get(models.Sample, sample_id)
    if not sample:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    self._session.delete(sample)
    if commit: self._session.commit()

    if not persist_session: self.close_session()

def query_samples(
    self, query: str,
    user_id: Optional[int] = None,
    limit: Optional[int] = 20
) -> list[SearchResult]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Sample).where(
        models.Sample.name.contains(query)
    )

    if limit is not None:
        res = res.limit(limit)

    res = res.all()
    res = [sample.to_search_result() for sample in res]

    if not persist_session: self.close_session()
    
    return res

