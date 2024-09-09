import math
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.sql import and_

from ... import models, PAGE_LIMIT
from ...categories import SampleStatus, SampleStatusEnum, AttributeTypeEnum, AccessType, AccessTypeEnum
from .. import exceptions


def create_sample(
    self, name: str, owner_id: int, project_id: int,
    status: SampleStatusEnum = SampleStatus.DRAFT
) -> models.Sample:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (project := self._session.get(models.Project, project_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Project with id '{project_id}', not found.")

    if (user := self._session.get(models.User, owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{owner_id}', not found.")

    sample = models.Sample(
        name=name.strip(),
        project_id=project_id,
        owner_id=owner_id,
        status_id=status.id
    )

    self._session.add(sample)
    project.num_samples += 1
    user.num_samples += 1
    
    self._session.commit()
    self._session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def get_sample(self, sample_id: int) -> Optional[models.Sample]:
    if not (persist_session := self._session is not None):
        self.open_session()

    sample = self._session.get(models.Sample, sample_id)

    if not persist_session:
        self.close_session()

    return sample


def get_samples(
    self, user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    library_id: Optional[int] = None,
    pool_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    status: Optional[SampleStatusEnum] = None,
    status_in: Optional[list[SampleStatusEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[models.Sample], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.Sample)

    if seq_request_id is not None:
        query = query.join(
            models.SampleLibraryLink,
            models.SampleLibraryLink.sample_id == models.Sample.id
        ).join(
            models.Library,
            models.Library.id == models.SampleLibraryLink.library_id
        ).where(
            models.Library.seq_request_id == seq_request_id
        )

    if user_id is not None:
        query = query.where(
            models.Sample.owner_id == user_id
        )

    if project_id is not None:
        query = query.where(
            models.Sample.project_id == project_id
        )

    if library_id is not None:
        query = query.join(
            models.SampleLibraryLink,
            models.SampleLibraryLink.sample_id == models.Sample.id
        ).where(
            models.SampleLibraryLink.library_id == library_id
        )

    if pool_id is not None:
        query = query.join(
            models.SampleLibraryLink,
            models.SampleLibraryLink.sample_id == models.Sample.id
        ).join(
            models.Library,
            models.Library.id == models.SampleLibraryLink.library_id
        ).where(
            models.Library.pool_id == pool_id
        )

    if status is not None:
        query = query.where(
            models.Sample.status_id == status.id
        )

    if status_in is not None:
        query = query.where(
            models.Sample.status_id.in_([s.id for s in status_in])
        )

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if sort_by is not None:
        attr = getattr(models.Sample, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)
    
    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    samples = query.all()

    if not persist_session:
        self.close_session()
        
    return samples, n_pages


def update_sample(self, sample: models.Sample) -> models.Sample:
    if not (persist_session := self._session is not None):
        self.open_session()

    self._session.add(sample)
    self._session.commit()
    self._session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def delete_sample(self, sample_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (sample := self._session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    sample.owner.num_samples -= 1
    sample.project.num_samples -= 1
    self._session.delete(sample)
    self._session.commit()

    if not persist_session:
        self.close_session()


def query_samples(
    self, word: str,
    user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    pool_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT
) -> list[models.Sample]:

    if not (persist_session := self._session is not None):
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
            models.SampleLibraryLink.sample_id == models.Sample.id
        ).join(
            models.Library,
            models.Library.id == models.SampleLibraryLink.library_id
        ).where(
            models.Library.seq_request_id == seq_request_id
        )

    if pool_id is not None:
        query = query.join(
            models.SampleLibraryLink,
            models.SampleLibraryLink.sample_id == models.Sample.id
        ).join(
            models.Library,
            models.Library.id == models.SampleLibraryLink.library_id
        ).where(
            models.Library.pool_id == pool_id
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


def set_sample_attribute(
    self, sample_id: int, value: str, type: AttributeTypeEnum, name: Optional[str]
) -> models.Sample:
    if not (persist_session := self._session is not None):
        self.open_session()

    if name is None:
        name = type.label
    else:
        name = name.lower().strip().replace(" ", "_")

    if (sample := self._session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}', not found.")
    
    if (attribute := self._session.query(models.SampleAttribute).where(
        and_(models.SampleAttribute.sample_id == sample_id, models.SampleAttribute.name == name)
    ).first()) is not None:
        attribute.value = value
    else:
        attribute = models.SampleAttribute(
            value=value,
            name=name,
            type_id=type.id
        )

    sample.attributes.append(attribute)

    self._session.add(sample)
    self._session.commit()
    self._session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def get_sample_attribute(
    self, sample_id: int, name: str
) -> Optional[models.SampleAttribute]:
    if not (persist_session := self._session is not None):
        self.open_session()

    name = name.lower()

    attribute = self._session.query(models.SampleAttribute).where(
        and_(
            models.SampleAttribute.sample_id == sample_id,
            models.SampleAttribute.name == name
        )
    ).first()

    if not persist_session:
        self.close_session()
    return attribute


def get_sample_attributes(
    self, sample_id: int
) -> list[models.SampleAttribute]:
    if not (persist_session := self._session is not None):
        self.open_session()

    attributes = self._session.query(models.SampleAttribute).where(
        models.SampleAttribute.sample_id == sample_id
    ).all()

    if not persist_session:
        self.close_session()
    return attributes


def get_user_sample_access_type(
    self, sample_id: int, user_id: int,
) -> Optional[AccessTypeEnum]:
    if not (persist_session := self._session is not None):
        self.open_session()

    sample: models.Sample
    if (sample := self._session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}', not found.")
    
    access_type: Optional[AccessTypeEnum] = None

    if sample.owner_id == user_id:
        access_type = AccessType.OWNER
    elif sample.library_links:
        for link in sample.library_links:
            if link.library.owner_id == user_id:
                access_type = AccessType.EDIT
                break
            elif link.library.seq_request.group_id is not None:
                if self.get_group_user_affiliation(user_id, link.library.seq_request.group_id) is not None:
                    access_type = AccessType.EDIT
                    break
    
    if not persist_session:
        self.close_session()

    return access_type