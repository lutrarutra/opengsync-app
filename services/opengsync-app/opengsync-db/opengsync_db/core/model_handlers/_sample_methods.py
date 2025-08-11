import math
from typing import Optional, TYPE_CHECKING, Callable

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
    status: SampleStatusEnum | None, flush: bool = True
) -> models.Sample:
    if not (persist_session := self._session is not None):
        self.open_session()

    sample = models.Sample(
        name=name.strip(),
        project_id=project_id,
        owner_id=owner_id,
        status_id=status.id if status is not None else None
    )

    self.session.add(sample)

    if flush:
        self.flush()

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
    query: Query, user_id: int | None = None,
    project_id: int | None = None,
    library_id: int | None = None,
    pool_id: int | None = None,
    seq_request_id: int | None = None,
    status: Optional[SampleStatusEnum] = None,
    status_in: Optional[list[SampleStatusEnum]] = None,
    custom_query: Callable[[Query], Query] | None = None,
) -> Query:
    if seq_request_id is not None:
        query = query.where(
            sa.exists().where(
                (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
                (models.Library.id == models.links.SampleLibraryLink.library_id) &
                (models.Library.seq_request_id == seq_request_id)
            )
        )

    if user_id is not None:
        query = query.where(models.Sample.owner_id == user_id)

    if project_id is not None:
        query = query.where(models.Sample.project_id == project_id)

    if library_id is not None:
        query = query.where(
            sa.exists().where(
                (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
                (models.Library.id == models.links.SampleLibraryLink.library_id) &
                (models.Library.id == library_id)
            )
        )

    if pool_id is not None:
        query = query.where(
            sa.exists().where(
                (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
                (models.Library.id == models.links.SampleLibraryLink.library_id) &
                (models.Library.pool_id == pool_id)
            )
        )

    if status is not None:
        query = query.where(models.Sample.status_id == status.id)

    if status_in is not None:
        query = query.where(models.Sample.status_id.in_([s.id for s in status_in]))

    if custom_query is not None:
        query = custom_query(query)

    return query


def get_samples(
    self: "DBHandler", user_id: int | None = None,
    project_id: int | None = None,
    library_id: int | None = None,
    pool_id: int | None = None,
    seq_request_id: int | None = None,
    status: Optional[SampleStatusEnum] = None,
    status_in: Optional[list[SampleStatusEnum]] = None,
    custom_query: Callable[[Query], Query] | None = None,
    limit: int | None = PAGE_LIMIT, offset: int | None = None,
    sort_by: Optional[str] = None, descending: bool = False,
    count_pages: bool = False
) -> tuple[list[models.Sample], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Sample)
    query = where(
        query, user_id=user_id, project_id=project_id, library_id=library_id,
        pool_id=pool_id, seq_request_id=seq_request_id, status=status, status_in=status_in,
        custom_query=custom_query
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

    if not persist_session:
        self.close_session()
    return sample


def delete_sample(self: "DBHandler", sample_id: int, flush: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (sample := self.session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    self.session.delete(sample)

    if flush:
        self.flush()

    if not persist_session:
        self.close_session()


def delete_oprhan_samples(
    self: "DBHandler", flush: bool = True
) -> None:
    if not (persist_session := self._session is not None):
        self.open_session()

    samples = self.session.query(models.Sample).where(
        ~sa.exists().where(models.links.SampleLibraryLink.sample_id == models.Sample.id)
    )

    for sample in samples:
        self.session.delete(sample)

    if flush:
        self.flush()

    if not persist_session:
        self.close_session()


def query_samples(
    self: "DBHandler", word: str,
    user_id: int | None = None,
    project_id: int | None = None,
    library_id: int | None = None,
    pool_id: int | None = None,
    seq_request_id: int | None = None,
    status: Optional[SampleStatusEnum] = None,
    status_in: Optional[list[SampleStatusEnum]] = None,
    limit: int | None = PAGE_LIMIT
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
    
    sample.set_attribute(key=name, value=value, type=type)

    self.session.add(sample)

    if not persist_session:
        self.close_session()
    return sample


def get_sample_attribute(self: "DBHandler", sample_id: int, name: str) -> models.SampleAttribute | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    name = name.lower().strip().replace(" ", "_")

    if (sample := self.session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}', not found.")
    
    attribute = sample.get_attribute(key=name)

    if not persist_session:
        self.close_session()
    return attribute


def delete_sample_attribute(
    self: "DBHandler", sample_id: int, name: str
) -> models.Sample:
    if not (persist_session := self._session is not None):
        self.open_session()

    name = name.lower().strip().replace(" ", "_")

    if (sample := self.session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}', not found.")
    
    if sample.get_attribute(key=name) is None:
        raise exceptions.ElementDoesNotExist(f"Sample attribute with name '{name}' does not exist in sample with id '{sample_id}'.")
    
    sample.delete_sample_attribute(key=name)

    self.session.add(sample)

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