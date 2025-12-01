import math
from datetime import datetime
from typing import Optional, Literal, Callable, Iterator

import sqlalchemy as sa
from sqlalchemy.orm import Query
from sqlalchemy.sql.base import ExecutableOption

from ... import to_utc
from ... import models, PAGE_LIMIT
from ...categories import (
    SeqRequestStatus, LibraryStatus, DataDeliveryModeEnum, SeqRequestStatusEnum,
    PoolStatus, DeliveryStatus, ReadTypeEnum, SampleStatus, PoolType,
    SubmissionTypeEnum, AccessType, AccessTypeEnum, SubmissionType,
    ProjectStatus, UserRole
)
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class SeqRequestBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query, status: Optional[SeqRequestStatusEnum] = None,
        status_in: Optional[list[SeqRequestStatusEnum]] = None,
        submission_type: Optional[SubmissionTypeEnum] = None,
        submission_type_in: Optional[list[SubmissionTypeEnum]] = None,
        show_drafts: bool = True, user_id: int | None = None,
        project_id: int | None = None,
        group_id: int | None = None,
        custom_query: Callable[[Query], Query] | None = None,
    ) -> Query:
        if status is not None:
            query = query.where(
                models.SeqRequest.status_id == status.id
            )

        if submission_type is not None:
            query = query.where(
                models.SeqRequest.submission_type_id == submission_type.id
            )

        if user_id is not None:
            query = query.where(
                sa.or_(
                    models.SeqRequest.requestor_id == user_id,
                    sa.exists().where(
                        (models.links.UserAffiliation.user_id == user_id) &
                        (models.links.UserAffiliation.group_id == models.SeqRequest.group_id)
                    ),
                )
            )

        if status_in is not None:
            status_ids = [status.id for status in status_in]
            query = query.where(
                models.SeqRequest.status_id.in_(status_ids)  # type: ignore
            )
        
        if submission_type_in is not None:
            submission_type_ids = [submission_type.id for submission_type in submission_type_in]
            query = query.where(
                models.SeqRequest.submission_type_id.in_(submission_type_ids)  # type: ignore
            )

        if not show_drafts:
            query = query.where(
                sa.or_(
                    models.SeqRequest.status_id != SeqRequestStatus.DRAFT.id,
                    models.SeqRequest.requestor_id == user_id
                )
            )

        if group_id is not None:
            query = query.where(models.SeqRequest.group_id == group_id)

        if project_id is not None:
            query = query.where(
                sa.exists().where(
                    (models.Sample.project_id == models.Project.id) &
                    (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
                    (models.Library.id == models.links.SampleLibraryLink.library_id) &
                    (models.Library.seq_request_id == models.SeqRequest.id) &
                    (models.Project.id == project_id)
                )
            )

        if custom_query is not None:
            query = custom_query(query)

        return query

    @DBBlueprint.transaction
    def create(
        self,
        name: str,
        description: str | None,
        requestor_id: int,
        group_id: int | None,
        billing_contact_id: int,
        data_delivery_mode: DataDeliveryModeEnum,
        read_type: ReadTypeEnum,
        submission_type: SubmissionTypeEnum,
        contact_person_id: int,
        organization_contact_id: int,
        bioinformatician_contact_id: int | None = None,
        read_length: int | None = None,
        num_lanes: int | None = None,
        special_requirements: str | None = None,
        billing_code: str | None = None,
        flush: bool = True
    ) -> models.SeqRequest:
        if (requestor := self.db.session.get(models.User, requestor_id)) is None:
            raise exceptions.ElementDoesNotExist(f"User with id '{requestor_id}', not found.")
        
        if group_id is not None:
            if self.db.session.get(models.Group, group_id) is None:
                raise exceptions.ElementDoesNotExist(f"Group with id '{group_id}', not found.")

        if self.db.session.get(models.Contact, billing_contact_id) is None:
            raise exceptions.ElementDoesNotExist(f"Contact with id '{billing_contact_id}', not found.")

        if (contact_person := self.db.session.get(models.Contact, contact_person_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Contact with id '{contact_person_id}', not found.")
        
        if self.db.session.get(models.Contact, organization_contact_id) is None:
            raise exceptions.ElementDoesNotExist(f"Contact with id '{organization_contact_id}', not found.")

        if bioinformatician_contact_id is not None:
            if (bioinformatician_contact := self.db.session.get(models.Contact, bioinformatician_contact_id)) is None:
                raise exceptions.ElementDoesNotExist(f"Contact with id '{bioinformatician_contact_id}', not found.")
        else:
            bioinformatician_contact = None
            
        seq_request = models.SeqRequest(
            name=name.strip(),
            group_id=group_id,
            description=description.strip() if description else None,
            requestor_id=requestor_id,
            read_length=read_length,
            num_lanes=num_lanes,
            read_type_id=read_type.id,
            special_requirements=special_requirements,
            billing_contact_id=billing_contact_id,
            submission_type_id=submission_type.id,
            contact_person_id=contact_person_id,
            organization_contact_id=organization_contact_id,
            bioinformatician_contact_id=bioinformatician_contact_id,
            status_id=SeqRequestStatus.DRAFT.id,
            data_delivery_mode_id=data_delivery_mode.id,
            billing_code=billing_code.strip() if billing_code else None,
        )

        self.db.session.add(seq_request)

        if flush:
            self.db.flush()

        return seq_request

    @DBBlueprint.transaction
    def get(self, seq_request_id: int, options: ExecutableOption | None = None) -> models.SeqRequest | None:
        if options is None:
            seq_request = self.db.session.get(models.SeqRequest, seq_request_id)
        else:
            seq_request = self.db.session.query(models.SeqRequest).options(
                options
            ).filter(models.SeqRequest.id == seq_request_id).first()
        return seq_request
    
    @DBBlueprint.transaction
    def find(
        self,
        status: Optional[SeqRequestStatusEnum] = None,
        status_in: Optional[list[SeqRequestStatusEnum]] = None,
        submission_type: Optional[SubmissionTypeEnum] = None,
        submission_type_in: Optional[list[SubmissionTypeEnum]] = None,
        show_drafts: bool = True,
        user_id: int | None = None,
        project_id: int | None = None,
        group_id: int | None = None,
        custom_query: Callable[[Query], Query] | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: str | None = None, descending: bool = False,
        count_pages: bool = False,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.SeqRequest], int | None]:
        query = self.db.session.query(models.SeqRequest)
        query = SeqRequestBP.where(
            query, status_in=status_in, submission_type_in=submission_type_in, submission_type=submission_type,
            show_drafts=show_drafts, user_id=user_id, group_id=group_id, status=status, project_id=project_id,
            custom_query=custom_query
        )
        if options is not None:
            query = query.options(options)

        if sort_by is not None:
            attr = getattr(models.SeqRequest, sort_by)
            if descending:
                attr = attr.desc()

            query = query.order_by(sa.nulls_last(attr))

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        seq_requests = query.all()

        return seq_requests, n_pages

    @DBBlueprint.transaction
    def submit(self, seq_request_id: int) -> models.SeqRequest:
        if (seq_request := self.db.session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request}', not found.")

        seq_request.status = SeqRequestStatus.SUBMITTED
        seq_request.timestamp_submitted_utc = to_utc(datetime.now())
        for library in seq_request.libraries:
            if library.status == LibraryStatus.DRAFT:
                library.status = LibraryStatus.SUBMITTED
                self.db.session.add(library)

        for pool in seq_request.pools:
            pool.status = PoolStatus.SUBMITTED
            self.db.session.add(pool)

        return seq_request

    @DBBlueprint.transaction
    def update(self, seq_request: models.SeqRequest):
        self.db.session.add(seq_request)

    @DBBlueprint.transaction
    def delete(self, seq_request_id: int, flush: bool = True) -> None:
        if (seq_request := self.db.session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")

        for library in seq_request.libraries:
            self.db.libraries.delete(library)

        for pool in seq_request.pools:
            if pool.type == PoolType.EXTERNAL:
                self.db.pools.delete(pool.id)

        self.db.session.delete(seq_request)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def query(
        self,
        name: str | None = None,
        requestor: str | None = None,
        group: str | None = None,
        status: Optional[SeqRequestStatusEnum] = None,
        status_in: Optional[list[SeqRequestStatusEnum]] = None,
        show_drafts: bool = True,
        user_id: int | None = None,
        group_id: int | None = None,
        limit: int | None = PAGE_LIMIT,
    ) -> list[models.SeqRequest]:
        query = self.db.session.query(models.SeqRequest)

        query = SeqRequestBP.where(query, status_in=status_in, show_drafts=show_drafts, user_id=user_id, group_id=group_id, status=status)

        if name is not None:
            query = query.order_by(
                sa.func.similarity(models.SeqRequest.name, name).desc()
            )
        elif requestor is not None:
            query = query.join(
                models.User,
                models.User.id == models.SeqRequest.requestor_id
            )
            query = query.order_by(
                sa.func.similarity(models.User.first_name + ' ' + models.User.last_name, requestor).desc()
            )
        elif group is not None:
            query = query.join(
                models.Group,
                models.Group.id == models.SeqRequest.group_id
            )
            query = query.order_by(
                sa.func.similarity(models.Group.name, group).desc()
            )
        else:
            raise ValueError("Either 'name', 'requestor', or 'group' must be provided.")

        if limit is not None:
            query = query.limit(limit)

        seq_requests = query.all()
        return seq_requests

    @DBBlueprint.transaction
    def add_share_email(self, seq_request_id: int, email: str) -> models.SeqRequest:
        if (seq_request := self.db.session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
        
        if self.db.session.query(models.links.SeqRequestDeliveryEmailLink).where(
            models.links.SeqRequestDeliveryEmailLink.seq_request_id == seq_request_id,
            models.links.SeqRequestDeliveryEmailLink.email == email
        ).first() is not None:
            raise exceptions.LinkAlreadyExists(f"SeqRequest with id '{seq_request_id}' already has a share link with email '{email}'.")

        seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(
            email=email, status_id=DeliveryStatus.PENDING.id
        ))

        self.db.session.add(seq_request)
        return seq_request

    @DBBlueprint.transaction
    def remove_share_email(self, seq_request_id: int, email: str) -> models.SeqRequest:
        if (seq_request := self.db.session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
        
        if (delivery_link := self.db.session.query(models.links.SeqRequestDeliveryEmailLink).where(
            models.links.SeqRequestDeliveryEmailLink.seq_request_id == seq_request_id,
            models.links.SeqRequestDeliveryEmailLink.email == email
        ).first()) is None:
            raise exceptions.ElementDoesNotExist(f"Share link with '{email}', not found.")

        seq_request.delivery_email_links.remove(delivery_link)
        self.db.session.delete(delivery_link)
        self.db.session.add(seq_request)
        return seq_request

    @DBBlueprint.transaction
    def process(self, seq_request_id: int, status: SeqRequestStatusEnum) -> models.SeqRequest:
        if (seq_request := self.db.session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")

        seq_request.status = status

        if seq_request.status in [SeqRequestStatus.DRAFT, SeqRequestStatus.REJECTED]:
            seq_request.timestamp_submitted_utc = None
            if seq_request.sample_submission_event_id is not None:
                self.db.session.delete(seq_request.sample_submission_event)
                seq_request.sample_submission_event = None
        
        if status == SeqRequestStatus.ACCEPTED:
            library_status = LibraryStatus.ACCEPTED
            pool_status = PoolStatus.ACCEPTED
        elif status == SeqRequestStatus.DRAFT:
            library_status = LibraryStatus.DRAFT
            pool_status = PoolStatus.DRAFT
        elif status == SeqRequestStatus.REJECTED:
            library_status = LibraryStatus.REJECTED
            pool_status = PoolStatus.REJECTED
        else:
            raise TypeError(f"Cannot process request to '{status}'.")

        for sample in seq_request.samples:
            if sample.status is None:
                continue  # Sample was not prepared in-house -> no specimen stored
            if status == SeqRequestStatus.ACCEPTED:
                sample.status = SampleStatus.WAITING_DELIVERY
            elif status == SeqRequestStatus.DRAFT:
                sample.status = SampleStatus.DRAFT
            elif status == SeqRequestStatus.REJECTED:
                sample.status = SampleStatus.REJECTED
        
        is_prepared = status == SeqRequestStatus.ACCEPTED
        for library in seq_request.libraries:
            if library.status == LibraryStatus.SUBMITTED:
                library.status = library_status
                
            if library_status != LibraryStatus.ACCEPTED:
                continue
            
            if library.pool_id is not None:
                library.status = LibraryStatus.POOLED

            is_prepared = is_prepared and library.status.id >= LibraryStatus.POOLED.id
        
        if status == SeqRequestStatus.ACCEPTED:
            seq_request.status = SeqRequestStatus.ACCEPTED

        for pool in seq_request.pools:
            pool.status = pool_status

        for project in self.db.projects.find(seq_request_id=seq_request_id)[0]:
            project.status = ProjectStatus.PROCESSING
            self.db.session.add(project)

        self.db.session.add(seq_request)
        return seq_request

    @DBBlueprint.transaction
    def get_access_type(self, seq_request: models.SeqRequest, user: models.User) -> AccessTypeEnum:
        if user.role == UserRole.DEACTIVATED:
            return AccessType.NONE
        if user.is_admin():
            return AccessType.ADMIN
        if user.is_insider():
            return AccessType.INSIDER
        if user == seq_request.requestor:
            return AccessType.OWNER

        has_access: bool = self.db.session.query(
            sa.exists().where(
                (models.links.UserAffiliation.user_id == user.id) &
                (models.links.UserAffiliation.group_id == seq_request.group_id)
            )
        ).scalar()

        if has_access:
            return AccessType.EDIT

        return AccessType.NONE

    @DBBlueprint.transaction
    def clone(self, seq_request_id: int, method: Literal["pooled", "indexed", "raw"]) -> models.SeqRequest:
        if method not in {"pooled", "indexed", "raw"}:
            raise ValueError(f"Method should be one of: {', '.join(['pooled', 'indexed', 'raw'])}")

        if (seq_request := self.db.session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
        
        if method == "raw":
            submission_type = SubmissionType.RAW_SAMPLES
        elif method == "indexed":
            submission_type = SubmissionType.UNPOOLED_LIBRARIES
        elif method == "pooled":
            submission_type = SubmissionType.POOLED_LIBRARIES

        cloned_request = self.create(
            name=f"RE: {seq_request.name}"[:models.SeqRequest.name.type.length],
            requestor_id=seq_request.requestor_id,
            group_id=seq_request.group_id,
            description=seq_request.description,
            billing_contact_id=seq_request.billing_contact_id,
            data_delivery_mode=seq_request.data_delivery_mode,
            read_type=seq_request.read_type,
            submission_type=submission_type,
            contact_person_id=seq_request.contact_person_id,
            organization_contact_id=seq_request.organization_contact_id,
            bioinformatician_contact_id=seq_request.bioinformatician_contact_id,
            read_length=seq_request.read_length,
            num_lanes=seq_request.num_lanes,
            special_requirements=seq_request.special_requirements,
            billing_code=seq_request.billing_code,
        )

        if method == "pooled":
            pools: dict[int, models.Pool] = {}
            for library in seq_request.libraries:
                cloned_library = self.db.libraries.clone(library_id=library.id, seq_request_id=cloned_request.id, indexed=True, status=LibraryStatus.POOLED)
                if library.pool_id is not None:
                    if library.pool_id not in pools.keys():
                        pools[library.pool_id] = self.db.pools.clone(library.pool_id, seq_request_id=cloned_request.id, status=PoolStatus.STORED)
                    self.db.libraries.add_to_pool(library_id=cloned_library.id, pool_id=pools[library.pool_id].id)
        elif method == "indexed":
            for library in seq_request.libraries:
                self.db.libraries.clone(library_id=library.id, seq_request_id=cloned_request.id, indexed=True, status=LibraryStatus.STORED)
        elif method == "raw":
            for library in seq_request.libraries:
                self.db.libraries.clone(library_id=library.id, seq_request_id=cloned_request.id, indexed=False, status=LibraryStatus.ACCEPTED)

        self.db.session.add(cloned_request)
        return cloned_request
    
    @DBBlueprint.transaction
    def __getitem__(self, id: int) -> models.SeqRequest:
        if (seq_request := self.get(id)) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{id}', not found.")
        
        return seq_request
    
    @DBBlueprint.transaction
    def iter(
        self,
        status: Optional[SeqRequestStatusEnum] = None,
        status_in: Optional[list[SeqRequestStatusEnum]] = None,
        submission_type: Optional[SubmissionTypeEnum] = None,
        submission_type_in: Optional[list[SubmissionTypeEnum]] = None,
        show_drafts: bool = True, user_id: int | None = None,
        project_id: int | None = None,
        group_id: int | None = None,
        custom_query: Callable[[Query], Query] | None = None,
        order_by: str | None = "id",
        limit: int | None = None,
        chunk_size: int = 1000
    ) -> Iterator[models.SeqRequest]:
        offset = 0
        query = self.db.session.query(models.SeqRequest)
        if order_by is not None:
            attr = getattr(models.SeqRequest, order_by)
            query = query.order_by(sa.nulls_last(attr))
        query = SeqRequestBP.where(
            query, status_in=status_in, submission_type_in=submission_type_in, submission_type=submission_type,
            show_drafts=show_drafts, user_id=user_id, group_id=group_id, status=status, project_id=project_id,
            custom_query=custom_query
        )
        offset = 0
        while True:
            chunk = query.limit(chunk_size).offset(offset).all()

            if not chunk:
                break
            
            for seq_request in chunk:
                yield seq_request

            if limit and offset + chunk_size >= limit:
                break
            
            offset += chunk_size
            
    @DBBlueprint.transaction
    def __iter__(self) -> Iterator[models.SeqRequest]:
        return self.iter()
    
    @DBBlueprint.transaction
    def __len__(self) -> int:
        return self.db.session.query(models.SeqRequest).count()
    