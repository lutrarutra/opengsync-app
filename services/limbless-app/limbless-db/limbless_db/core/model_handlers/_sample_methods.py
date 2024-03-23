import math
from typing import Optional

import sqlalchemy as sa

from ... import models, PAGE_LIMIT
from .. import exceptions


def create_sample(
    self, name: str,
    owner_id: int,
    project_id: int,
    commit: bool = True
) -> models.Sample:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (project := self._session.get(models.Project, project_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Project with id '{project_id}', not found.")

    if (user := self._session.get(models.User, owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{owner_id}', not found.")

    sample = models.Sample(
        name=name,
        project_id=project_id,
        owner_id=owner_id
    )

    self._session.add(sample)
    project.num_samples += 1
    user.num_samples += 1
    
    if commit:
        self._session.commit()
        self._session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def get_sample(self, sample_id: int) -> Optional[models.Sample]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.Sample, sample_id)

    if not persist_session:
        self.close_session()
    return res


def get_samples(
    self, user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.Sample], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sample)

    if sort_by is not None:
        attr = getattr(models.Sample, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    if user_id is not None:
        query = query.where(
            models.Sample.owner_id == user_id
        )

    if project_id is not None:
        query = query.where(
            models.Sample.project_id == project_id
        )

    if seq_request_id is not None:
        query = query.join(
            models.SampleLibraryLink,
            models.SampleLibraryLink.sample_id == models.Sample.id,
        ).join(
            models.Library,
            models.Library.id == models.SampleLibraryLink.library_id,
        ).where(
            models.Library.seq_request_id == seq_request_id,
        ).distinct()

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1
    
    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    samples = query.all()

    if not persist_session:
        self.close_session()
        
    return samples, n_pages


def update_sample(
    self, sample_id: int,
    name: Optional[str] = None,
    commit: bool = True
) -> models.Sample:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sample = self._session.get(models.Sample, sample_id)
    if not sample:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")

    if name is not None:
        sample.name = name

    if commit:
        self._session.commit()
        self._session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def delete_sample(
    self, sample_id: int,
    commit: bool = True
) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (sample := self._session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    sample.owner.num_samples -= 1
    sample.project.num_samples -= 1
    self._session.delete(sample)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def query_samples(
    self, word: str,
    user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT
) -> list[models.Sample]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sample)
    
    if user_id is not None:
        query = query.where(
            models.Sample.owner_id == user_id
        )

    if project_id is not None:
        query = query.where(
            models.Sample.project_id == project_id
        )

    if seq_request_id is not None:
        query = query.join(
            models.SampleLibraryLink,
            models.SampleLibraryLink.sample_id == models.Sample.id,
        ).join(
            models.Library,
            models.Library.id == models.SampleLibraryLink.library_id,
        ).where(
            models.Library.seq_request_id == seq_request_id,
        )

    query = query.order_by(
        sa.func.similarity(models.Sample.name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    res = query.all()

    if not persist_session:
        self.close_session()

    return res