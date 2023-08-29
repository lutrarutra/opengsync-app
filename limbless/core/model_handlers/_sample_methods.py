from typing import Optional, Union

from ... import models
from .. import exceptions

def create_sample(
        self, name: str,
        organism_tax_id: int,
        project_id: int,
        index1: str, index2: Optional[str] = None,
        commit: bool = True
    ) -> models.Sample:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if not self._session.get(models.Project, project_id):
        raise exceptions.ElementDoesNotExist(f"Project with id '{project_id}', not found.")

    organism = self._session.get(models.Organism, organism_tax_id)
    if not organism:
        raise exceptions.ElementDoesNotExist(f"Organism with tax_id '{organism_tax_id}', not found.")

    sample = models.Sample(
        name=name,
        organism_id=organism.tax_id,
        index1=index1, index2=index2,
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
        organism: Optional[str] = None,
        index1: Optional[str] = None,
        index2: Optional[str] = None,
        commit: bool = True
    ) -> models.Sample:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sample = self._session.get(models.Sample, sample_id)
    if not sample:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")

    if name is not None: sample.name = name
    if organism is not None: sample.organism = organism
    if index1 is not None: sample.index1 = index1
    if index2 is not None: sample.index2 = index2

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