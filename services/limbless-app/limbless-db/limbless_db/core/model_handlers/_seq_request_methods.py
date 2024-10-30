import math
from datetime import datetime
from typing import Optional, TYPE_CHECKING, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Query
from sqlalchemy.sql.operators import or_

if TYPE_CHECKING:
    from ..DBHandler import DBHandler

from ... import to_utc
from ... import models, PAGE_LIMIT
from ...categories import SeqRequestStatus, FileType, LibraryStatus, DataDeliveryModeEnum, SeqRequestStatusEnum, PoolStatus, DeliveryStatus, ReadTypeEnum, SampleStatus, PoolType, SubmissionTypeEnum, AccessType, AccessTypeEnum
from .. import exceptions


def create_seq_request(
    self: "DBHandler", name: str,
    description: Optional[str],
    requestor_id: int,
    group_id: Optional[int],
    billing_contact_id: int,
    data_delivery_mode: DataDeliveryModeEnum,
    read_type: ReadTypeEnum,
    submission_type: SubmissionTypeEnum,
    contact_person_id: int,
    organization_contact_id: int,
    bioinformatician_contact_id: Optional[int] = None,
    read_length: Optional[int] = None,
    num_lanes: Optional[int] = None,
    special_requirements: Optional[str] = None,
    billing_code: Optional[str] = None,
) -> models.SeqRequest:

    if not (persist_session := self._session is not None):
        self.open_session()

    if (requestor := self.session.get(models.User, requestor_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{requestor_id}', not found.")
    
    if group_id is not None:
        if self.session.get(models.Group, group_id) is None:
            raise exceptions.ElementDoesNotExist(f"Group with id '{group_id}', not found.")

    if self.session.get(models.Contact, billing_contact_id) is None:
        raise exceptions.ElementDoesNotExist(f"Contact with id '{billing_contact_id}', not found.")

    if self.session.get(models.Contact, contact_person_id) is None:
        raise exceptions.ElementDoesNotExist(f"Contact with id '{contact_person_id}', not found.")
    
    if self.session.get(models.Contact, organization_contact_id) is None:
        raise exceptions.ElementDoesNotExist(f"Contact with id '{organization_contact_id}', not found.")

    if bioinformatician_contact_id is not None:
        if (bioinformatician_contact := self.session.get(models.Contact, bioinformatician_contact_id)) is None:
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

    requestor.num_seq_requests += 1

    seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(
        email=requestor.email,
        status_id=DeliveryStatus.PENDING.id,
    ))
    self.session.add(seq_request)
    self.session.add(requestor)
    self.session.commit()
    self.session.refresh(seq_request)

    if bioinformatician_contact is not None:
        seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(
            email=bioinformatician_contact.email,
            status_id=DeliveryStatus.PENDING.id,
        ))
        self.session.add(seq_request)
        self.session.commit()
        self.session.refresh(seq_request)

    if not persist_session:
        self.close_session()

    return seq_request


def get_seq_request(self: "DBHandler", seq_request_id: int) -> Optional[models.SeqRequest]:
    if not (persist_session := self._session is not None):
        self.open_session()

    seq_request = self.session.get(models.SeqRequest, seq_request_id)

    if not persist_session:
        self.close_session()
    return seq_request


def where(
    query: Query, status: Optional[SeqRequestStatusEnum] = None,
    status_in: Optional[list[SeqRequestStatusEnum]] = None,
    show_drafts: bool = True, user_id: Optional[int] = None,
    group_id: Optional[int] = None
) -> Query:
    if status is not None:
        query = query.where(
            models.SeqRequest.status_id == status.id
        )

    if user_id is not None:
        query = query.where(
            models.SeqRequest.requestor_id == user_id
        )

    if status_in is not None:
        status_ids = [status.id for status in status_in]
        query = query.where(
            models.SeqRequest.status_id.in_(status_ids)  # type: ignore
        )

    if not show_drafts:
        query = query.where(
            or_(
                models.SeqRequest.status_id != SeqRequestStatus.DRAFT.id,
                models.SeqRequest.requestor_id == user_id
            )
        )

    if group_id is not None:
        query = query.where(
            models.SeqRequest.group_id == group_id
        )

    return query


def get_seq_requests(
    self: "DBHandler",
    status: Optional[SeqRequestStatusEnum] = None,
    status_in: Optional[list[SeqRequestStatusEnum]] = None,
    show_drafts: bool = True,
    sort_by: Optional[str] = None, descending: bool = False,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
) -> tuple[list[models.SeqRequest], int]:

    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.SeqRequest)

    query = where(query, status_in=status_in, show_drafts=show_drafts, user_id=user_id, group_id=group_id, status=status)

    if sort_by is not None:
        attr = getattr(models.SeqRequest, sort_by)
        if descending:
            attr = attr.desc()

        query = query.order_by(sa.nulls_last(attr))

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    seq_requests = query.all()

    if not persist_session:
        self.close_session()

    return seq_requests, n_pages


def submit_seq_request(self: "DBHandler", seq_request_id: int) -> models.SeqRequest:
    if not (persist_session := self._session is not None):
        self.open_session()

    seq_request: Optional[models.SeqRequest]
    if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request}', not found.")

    seq_request.status = SeqRequestStatus.SUBMITTED
    seq_request.timestamp_submitted_utc = to_utc(datetime.now())
    for library in seq_request.libraries:
        if library.status == LibraryStatus.DRAFT:
            library.status = LibraryStatus.SUBMITTED
            self.session.add(library)

    for sample in seq_request.samples:
        if sample.status == SampleStatus.DRAFT:
            sample.status = SampleStatus.SUBMITTED
            self.session.add(sample)

    for pool in seq_request.pools:
        pool.status = PoolStatus.SUBMITTED
        self.session.add(pool)

    self.session.commit()
    self.session.refresh(seq_request)

    if not persist_session:
        self.close_session()

    return seq_request


def update_seq_request(
    self: "DBHandler", seq_request: models.SeqRequest,
    commit: bool = True
) -> models.SeqRequest:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(seq_request)

    if commit:
        self.session.commit()
        self.session.refresh(seq_request)
        self.session.refresh(seq_request.billing_contact)
        self.session.refresh(seq_request.contact_person)
        if seq_request.bioinformatician_contact_id is not None:
            self.session.refresh(seq_request.bioinformatician_contact)

    if not persist_session:
        self.close_session()

    return seq_request


def delete_seq_request(self: "DBHandler", seq_request_id: int) -> None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")

    for library in seq_request.libraries:
        self.delete_library(library.id)

    for pool in seq_request.pools:
        if pool.type == PoolType.EXTERNAL:
            self.delete_pool(pool.id)

    seq_request.requestor.num_seq_requests -= 1
    self.session.delete(seq_request)
    self.session.commit()

    if not persist_session:
        self.close_session()


def query_seq_requests(
    self: "DBHandler",
    name: Optional[str] = None,
    requestor: Optional[str] = None,
    group: Optional[str] = None,
    status: Optional[SeqRequestStatusEnum] = None,
    status_in: Optional[list[SeqRequestStatusEnum]] = None,
    show_drafts: bool = True,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT,
) -> list[models.SeqRequest]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.SeqRequest)

    query = where(query, status_in=status_in, show_drafts=show_drafts, user_id=user_id, group_id=group_id, status=status)

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

    if not persist_session:
        self.close_session()
    return seq_requests


def add_seq_request_share_email(self: "DBHandler", seq_request_id: int, email: str) -> models.SeqRequest:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
    
    if self.session.query(models.links.SeqRequestDeliveryEmailLink).where(
        models.links.SeqRequestDeliveryEmailLink.seq_request_id == seq_request_id,
        models.links.SeqRequestDeliveryEmailLink.email == email
    ).first() is not None:
        raise exceptions.LinkAlreadyExists(f"SeqRequest with id '{seq_request_id}' already has a share link with email '{email}'.")

    seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(
        email=email, status_id=DeliveryStatus.PENDING.id
    ))

    self.session.add(seq_request)
    self.session.commit()
    self.session.refresh(seq_request)

    if not persist_session:
        self.close_session()

    return seq_request


def remove_seq_request_share_email(self: "DBHandler", seq_request_id: int, email: str) -> models.SeqRequest:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
    
    if (delivery_link := self.session.query(models.links.SeqRequestDeliveryEmailLink).where(
        models.links.SeqRequestDeliveryEmailLink.seq_request_id == seq_request_id,
        models.links.SeqRequestDeliveryEmailLink.email == email
    ).first()) is None:
        raise exceptions.ElementDoesNotExist(f"Share link with '{email}', not found.")

    seq_request.delivery_email_links.remove(delivery_link)
    self.session.delete(delivery_link)
    self.session.add(seq_request)
    self.session.commit()
    self.session.refresh(seq_request)

    if not persist_session:
        self.close_session()
    return seq_request


def process_seq_request(self: "DBHandler", seq_request_id: int, status: SeqRequestStatusEnum) -> models.SeqRequest:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")

    seq_request.status = status

    if seq_request.status in [SeqRequestStatus.DRAFT, SeqRequestStatus.REJECTED]:
        seq_request.timestamp_submitted_utc = None
        if seq_request.sample_submission_event_id is not None:
            self.session.delete(seq_request.sample_submission_event)
            seq_request.sample_submission_event = None
    
    if status == SeqRequestStatus.ACCEPTED:
        sample_status = SampleStatus.ACCEPTED
        library_status = LibraryStatus.ACCEPTED
        pool_status = PoolStatus.ACCEPTED
    elif status == SeqRequestStatus.DRAFT:
        sample_status = SampleStatus.DRAFT
        library_status = LibraryStatus.DRAFT
        pool_status = PoolStatus.DRAFT
    elif status == SeqRequestStatus.REJECTED:
        sample_status = SampleStatus.REJECTED
        library_status = LibraryStatus.REJECTED
        pool_status = PoolStatus.REJECTED
    else:
        raise TypeError(f"Cannot process request to '{status}'.")
    
    for sample in seq_request.samples:
        sample.status = sample_status
        if sample_status != SampleStatus.ACCEPTED:
            continue
        
        is_prepared = True
        for library_link in sample.library_links:
            if library_link.library.pool_id is None:
                is_prepared = False
                break
        if is_prepared:
            sample.status = SampleStatus.PREPARED
    
    is_prepared = status == SeqRequestStatus.ACCEPTED
    for library in seq_request.libraries:
        library.status = library_status
        if library_status != LibraryStatus.ACCEPTED:
            continue
        
        if library.pool_id is not None:
            library.status = LibraryStatus.POOLED

        is_prepared = is_prepared and library.status == LibraryStatus.POOLED
    
    if status == SeqRequestStatus.ACCEPTED:
        seq_request.status = SeqRequestStatus.PREPARED if is_prepared else SeqRequestStatus.ACCEPTED

    for pool in seq_request.pools:
        pool.status = pool_status

    self.session.add(seq_request)
    self.session.commit()
    self.session.refresh(seq_request)

    if not persist_session:
        self.close_session()

    return seq_request


def get_user_seq_request_access_type(
    self: "DBHandler", seq_request_id: int, user_id: int
) -> Optional[AccessTypeEnum]:
    if not (persist_session := self._session is not None):
        self.open_session()

    access_type: Optional[AccessTypeEnum] = None

    if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
    
    if seq_request.requestor_id == user_id:
        access_type = AccessType.OWNER
    elif seq_request.group_id is not None:
        if self.session.query(models.links.UserAffiliation).where(
            models.links.UserAffiliation.user_id == user_id,
            models.links.UserAffiliation.group_id == seq_request.group_id
        ).first() is not None:
            access_type = AccessType.EDIT

    if not persist_session:
        self.close_session()

    return access_type


def clone_seq_request(self: "DBHandler", seq_request_id: int, method: Literal["pooled", "indexed", "raw"]) -> models.SeqRequest:
    if method not in {"pooled", "indexed", "raw"}:
        raise ValueError(f"Method should be one of: {', '.join(['pooled', 'indexed', 'raw'])}")
    
    if not (persist_session := self._session is not None):
        self.open_session()

    if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")

    cloned_request = self.create_seq_request(
        name=f"RE: {seq_request.name}"[:models.SeqRequest.name.type.length],
        requestor_id=seq_request.requestor_id,
        group_id=seq_request.group_id,
        description=seq_request.description,
        billing_contact_id=seq_request.billing_contact_id,
        data_delivery_mode=seq_request.data_delivery_mode,
        read_type=seq_request.read_type,
        submission_type=seq_request.submission_type,
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
            cloned_library = self.clone_library(library_id=library.id, seq_request_id=cloned_request.id, indexed=True)
            if library.pool_id is not None:
                if library.pool_id not in pools.keys():
                    pools[library.pool_id] = self.clone_pool(library.pool_id, seq_request_id=seq_request.id)
                self.pool_library(library_id=cloned_library.id, pool_id=pools[library.pool_id].id)

    elif method == "indexed":
        for library in seq_request.libraries:
            self.clone_library(library_id=library.id, seq_request_id=cloned_request.id, indexed=True)
    elif method == "raw":
        for library in seq_request.libraries:
            self.clone_library(library_id=library.id, seq_request_id=cloned_request.id, indexed=False)

    self.session.add(cloned_request)
    self.session.commit()
    self.session.refresh(cloned_request)

    if not persist_session:
        self.close_session()

    return cloned_request