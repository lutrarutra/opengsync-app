import math
from typing import Optional, Callable

import sqlalchemy as sa
from sqlalchemy.orm import Query

from ... import models, PAGE_LIMIT
from ...categories import SampleStatusEnum, AttributeType, AttributeTypeEnum, AccessType, AccessTypeEnum
from .. import exceptions
from ..DBBlueprint import DBBlueprint


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


class SampleBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, name: str, owner_id: int, project_id: int,
        status: SampleStatusEnum | None, flush: bool = True
    ) -> models.Sample:

        sample = models.Sample(
            name=name.strip(),
            project_id=project_id,
            owner_id=owner_id,
            status_id=status.id if status is not None else None
        )

        self.db.session.add(sample)

        if flush:
            self.db.flush()

        return sample

    @DBBlueprint.transaction
    def get(self, sample_id: int) -> models.Sample | None:
        sample = self.db.session.get(models.Sample, sample_id)
        return sample

    @DBBlueprint.transaction
    def find(
        self, user_id: int | None = None,
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

        query = self.db.session.query(models.Sample)
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
        return samples, n_pages

    @DBBlueprint.transaction
    def update(self, sample: models.Sample) -> models.Sample:
        self.db.session.add(sample)
        return sample

    @DBBlueprint.transaction
    def delete(self, sample_id: int, flush: bool = True):
        if (sample := self.db.session.get(models.Sample, sample_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
        
        self.db.session.delete(sample)
        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def delete_orphan(
        self, flush: bool = True
    ) -> None:

        samples = self.db.session.query(models.Sample).where(
            ~sa.exists().where(models.links.SampleLibraryLink.sample_id == models.Sample.id)
        )

        for sample in samples:
            self.db.session.delete(sample)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def query(
        self, word: str,
        user_id: int | None = None,
        project_id: int | None = None,
        library_id: int | None = None,
        pool_id: int | None = None,
        seq_request_id: int | None = None,
        status: Optional[SampleStatusEnum] = None,
        status_in: Optional[list[SampleStatusEnum]] = None,
        limit: int | None = PAGE_LIMIT
    ) -> list[models.Sample]:
        query = self.db.session.query(models.Sample)
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
        return res

    @DBBlueprint.transaction
    def set_attribute(
        self, sample_id: int, value: str, type: AttributeTypeEnum, name: Optional[str]
    ) -> models.Sample:

        if type == AttributeType.CUSTOM:
            if name is None:
                raise ValueError("Attribute type is not custom, name must be provided.")
            name = name.lower().strip().replace(" ", "_")
        else:
            name = type.label

        if (sample := self.db.session.get(models.Sample, sample_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}', not found.")
        
        sample.set_attribute(key=name, value=value, type=type)

        self.db.session.add(sample)
        return sample

    @DBBlueprint.transaction
    def get_attribute(self, sample_id: int, name: str) -> models.SampleAttribute | None:
        name = name.lower().strip().replace(" ", "_")

        if (sample := self.db.session.get(models.Sample, sample_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}', not found.")
        
        attribute = sample.get_attribute(key=name)
        return attribute

    @DBBlueprint.transaction
    def delete_attribute(
        self, sample_id: int, name: str
    ) -> models.Sample:
        name = name.lower().strip().replace(" ", "_")

        if (sample := self.db.session.get(models.Sample, sample_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}', not found.")
        
        if sample.get_attribute(key=name) is None:
            raise exceptions.ElementDoesNotExist(f"Sample attribute with name '{name}' does not exist in sample with id '{sample_id}'.")
        
        sample.delete_sample_attribute(key=name)

        self.db.session.add(sample)
        return sample

    @DBBlueprint.transaction
    def get_access_type(self, sample_id: int, user_id: int) -> AccessTypeEnum | None:
        if (sample := self.db.session.get(models.Sample, sample_id)) is None:
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
        
        return access_type
    
    @DBBlueprint.transaction
    def __getitem__(self, sample_id: int) -> models.Sample:
        """Get a sample by its ID."""
        if (sample := self.db.session.get(models.Sample, sample_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}' does not exist.")
        return sample