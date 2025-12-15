import math
from typing import Optional, Callable

import sqlalchemy as sa
from sqlalchemy.orm import Query
from sqlalchemy.sql.base import ExecutableOption

from ... import models, PAGE_LIMIT
from ...categories import SampleStatusEnum, AttributeType, AttributeTypeEnum, AccessType, AccessTypeEnum, UserRole
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class SampleBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query, user_id: int | None = None,
        project_id: int | None = None,
        library_id: int | None = None,
        pool_id: int | None = None,
        seq_request_id: int | None = None,
        lab_prep_id: int | None = None,
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

        if lab_prep_id is not None:
            query = query.where(
                sa.exists().where(
                    (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
                    (models.Library.id == models.links.SampleLibraryLink.library_id) &
                    (models.Library.lab_prep_id == lab_prep_id)
                )
            )

        if status is not None:
            query = query.where(models.Sample.status_id == status.id)

        if status_in is not None:
            query = query.where(models.Sample.status_id.in_([s.id for s in status_in]))

        if custom_query is not None:
            query = custom_query(query)

        return query

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
    def get(self, sample_id: int, options: ExecutableOption | None = None) -> models.Sample | None:
        if options is not None:
            sample = self.db.session.query(models.Sample).options(options).filter(models.Sample.id == sample_id).first()
        else:
            sample = self.db.session.get(models.Sample, sample_id)
        return sample

    @DBBlueprint.transaction
    def find(
        self, user_id: int | None = None,
        project_id: int | None = None,
        library_id: int | None = None,
        pool_id: int | None = None,
        lab_prep_id: int | None = None,
        seq_request_id: int | None = None,
        status: Optional[SampleStatusEnum] = None,
        status_in: Optional[list[SampleStatusEnum]] = None,
        custom_query: Callable[[Query], Query] | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        page: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        options: ExecutableOption | None = None
    ) -> tuple[list[models.Sample], int | None]:

        query = self.db.session.query(models.Sample)
        query = SampleBP.where(
            query, user_id=user_id, project_id=project_id, library_id=library_id, lab_prep_id=lab_prep_id,
            pool_id=pool_id, seq_request_id=seq_request_id, status=status, status_in=status_in,
            custom_query=custom_query
        )
        if options is not None:
            query = query.options(options)

        if sort_by is not None:
            attr = getattr(models.Sample, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        if page is not None:
            if limit is None:
                raise ValueError("Limit must be provided when page is provided")
            
            count = query.count()
            n_pages = math.ceil(count / limit)
            query = query.offset(min(page, max(0, n_pages - (count % limit == 0))) * limit)
        else:
            n_pages = None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        samples = query.all()
        return samples, n_pages

    @DBBlueprint.transaction
    def update(self, sample: models.Sample):
        self.db.session.add(sample)

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
        lab_prep_id: int | None = None,
        status: Optional[SampleStatusEnum] = None,
        status_in: Optional[list[SampleStatusEnum]] = None,
        limit: int | None = PAGE_LIMIT
    ) -> list[models.Sample]:
        query = self.db.session.query(models.Sample)
        query = SampleBP.where(
            query, user_id=user_id, project_id=project_id, library_id=library_id, lab_prep_id=lab_prep_id,
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
    def get_access_type(self, sample: models.Sample, user: models.User) -> AccessTypeEnum:
        if user.role == UserRole.DEACTIVATED:
            return AccessType.NONE
        if user.is_admin():
            return AccessType.ADMIN
        if user.is_insider():
            return AccessType.INSIDER
        if user == sample.owner:
            return AccessType.OWNER
        
        affiliation_exists: bool = self.db.session.query(
            sa.exists().where(
                (models.links.UserAffiliation.user_id == user.id) &
                (models.SeqRequest.group_id == models.links.UserAffiliation.group_id) &
                (models.Library.seq_request_id == models.SeqRequest.id) &
                (models.links.SampleLibraryLink.sample_id == sample.id) &
                (models.links.SampleLibraryLink.library_id == models.Library.id)
            )
        ).scalar()

        if affiliation_exists:
            return AccessType.EDIT

        return AccessType.NONE

    @DBBlueprint.transaction
    def is_in_seq_request(
        self, sample_id: int, seq_request_id: int
    ) -> bool:
        
        query = self.db.session.query(models.Sample)

        query = query.join(
            models.links.SampleLibraryLink,
            models.links.SampleLibraryLink.sample_id == sample_id,
        ).join(
            models.Library,
            models.Library.id == models.links.SampleLibraryLink.library_id,
        ).where(
            models.Library.seq_request_id == seq_request_id,
        )
        res = query.first() is not None
        return res
    
    @DBBlueprint.transaction
    def __getitem__(self, sample_id: int) -> models.Sample:
        """Get a sample by its ID."""
        if (sample := self.db.session.get(models.Sample, sample_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Sample with id '{sample_id}' does not exist.")
        return sample