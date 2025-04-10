import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Query
from sqlalchemy.sql import and_

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from ...categories import SampleStatusEnum, AttributeType, AttributeTypeEnum, AccessType, AccessTypeEnum
from .. import exceptions


def create_sample(
    self: "DBHandler", name: str, owner_id: int, project_id: int,
    status: SampleStatusEnum | None
) -> models.Sample:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (project := self.session.get(models.Project, project_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Project with id '{project_id}', not found.")

    if (user := self.session.get(models.User, owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{owner_id}', not found.")

    sample = models.Sample(
        name=name.strip(),
        project_id=project_id,
        owner_id=owner_id,
        status_id=status.id if status is not None else None
    )

    self.session.add(sample)
    project.num_samples += 1
    user.num_samples += 1
    
    self.session.commit()
    self.session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def get_sample(self: "DBHandler", sample_id: int) -> models.Sample | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    sample = self.session.get(models.Sample, sample_id)

    if not persist_session:
        self.close_session()

    return sample


def where(
    query: Query, user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    library_id: Optional[int] = None,
    pool_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    status: Optional[SampleStatusEnum] = None,
    status_in: Optional[list[SampleStatusEnum]] = None
) -> Query:
    if seq_request_id is not None:
        query = query.join(
            models.links.SampleLibraryLink,
            models.links.SampleLibraryLink.sample_id == models.Sample.id
        ).join(
            models.Library,
            models.Library.id == models.links.SampleLibraryLink.library_id
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
            models.links.SampleLibraryLink,
            models.links.SampleLibraryLink.sample_id == models.Sample.id
        ).where(
            models.links.SampleLibraryLink.library_id == library_id
        )

    if pool_id is not None:
        query = query.join(
            models.links.SampleLibraryLink,
            models.links.SampleLibraryLink.sample_id == models.Sample.id
        ).join(
            models.Library,
            models.Library.id == models.links.SampleLibraryLink.library_id
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

    return query


def get_samples(
    self: "DBHandler", user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    library_id: Optional[int] = None,
    pool_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    status: Optional[SampleStatusEnum] = None,
    status_in: Optional[list[SampleStatusEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    count_pages: bool = False
) -> tuple[list[models.Sample], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Sample)
    query = where(
        query, user_id=user_id, project_id=project_id, library_id=library_id,
        pool_id=pool_id, seq_request_id=seq_request_id, status=status, status_in=status_in
    )
    n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

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


def update_sample(self: "DBHandler", sample: models.Sample) -> models.Sample:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(sample)
    self.session.commit()
    self.session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def delete_sample(self: "DBHandler", sample_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (sample := self.session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    sample.owner.num_samples -= 1
    sample.project.num_samples -= 1
    self.session.delete(sample)
    self.session.commit()

    if not persist_session:
        self.close_session()


def query_samples(
    self: "DBHandler", word: str,
    user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    library_id: Optional[int] = None,
    pool_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    status: Optional[SampleStatusEnum] = None,
    status_in: Optional[list[SampleStatusEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT
) -> list[models.Sample]:

    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Sample)
    query = where(
        query, user_id=user_id, project_id=project_id, library_id=library_id,
        pool_id=pool_id, seq_request_id=seq_request_id, status=status, status_in=status_in
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
    self: "DBHandler", sample_id: int, value: str, type: AttributeTypeEnum, name: Optional[str]
) -> models.Sample:
    if not (persist_session := self._session is not None):
        self.open_session()

    if type == AttributeType.CUSTOM:
        if name is None:
            raise ValueError("Attribute type is not custom, name must be provided.")
        name = name.lower().strip().replace(" ", "_")
    else:
        name = type.label

    if (sample := self.session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}', not found.")
    
    if (attribute := self.session.query(models.SampleAttribute).where(
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

    self.session.add(sample)
    self.session.commit()
    self.session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def get_sample_attribute(self: "DBHandler", sample_id: int, name: str) -> models.SampleAttribute | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    name = name.lower().strip().replace(" ", "_")

    attribute = self.session.query(models.SampleAttribute).where(
        and_(
            models.SampleAttribute.sample_id == sample_id,
            models.SampleAttribute.name == name
        )
    ).first()

    if not persist_session:
        self.close_session()
    return attribute


def get_sample_attributes(
    self: "DBHandler", sample_id: int
) -> list[models.SampleAttribute]:
    if not (persist_session := self._session is not None):
        self.open_session()

    attributes = self.session.query(models.SampleAttribute).where(
        models.SampleAttribute.sample_id == sample_id
    ).all()

    if not persist_session:
        self.close_session()
    return attributes


def delete_sample_attribute(
    self: "DBHandler", sample_id: int, name: str
) -> models.Sample:
    if not (persist_session := self._session is not None):
        self.open_session()

    name = name.lower().strip().replace(" ", "_")

    if (sample := self.session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}', not found.")
    
    if (attribute := self.session.query(models.SampleAttribute).where(
        and_(
            models.SampleAttribute.sample_id == sample_id,
            models.SampleAttribute.name == name
        )
    ).first()) is not None:
        sample.attributes.remove(attribute)
        self.session.delete(attribute)

    self.session.add(sample)
    self.session.commit()
    self.session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def get_user_sample_access_type(self: "DBHandler", sample_id: int, user_id: int) -> AccessTypeEnum | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (sample := self.session.get(models.Sample, sample_id)) is None:
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