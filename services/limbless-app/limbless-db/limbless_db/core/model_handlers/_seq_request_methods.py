import math
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.sql.operators import and_

from ... import models, PAGE_LIMIT
from ...categories import SeqRequestStatus, ReadTypeEnum, FileType, LibraryStatus, DataDeliveryModeEnum, SeqRequestStatusEnum, PoolStatus, DeliveryStatus
from .. import exceptions


def create_seq_request(
    self, name: str,
    description: Optional[str],
    requestor_id: int,
    contact_person_id: int,
    billing_contact_id: int,
    seq_type: ReadTypeEnum,
    data_delivery_mode: DataDeliveryModeEnum,
    organization_name: str,
    organization_address: str,
    num_cycles_read_1: Optional[int] = None,
    num_cycles_index_1: Optional[int] = None,
    num_cycles_index_2: Optional[int] = None,
    num_cycles_read_2: Optional[int] = None,
    read_length: Optional[int] = None,
    num_lanes: Optional[int] = None,
    special_requirements: Optional[str] = None,
    bioinformatician_contact_id: Optional[int] = None,
    organization_department: Optional[str] = None,
    billing_code: Optional[str] = None,
) -> models.SeqRequest:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (requestor := self._session.get(models.User, requestor_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{requestor_id}', not found.")

    if self._session.get(models.Contact, billing_contact_id) is None:
        raise exceptions.ElementDoesNotExist(f"Contact with id '{billing_contact_id}', not found.")

    if self._session.get(models.Contact, contact_person_id) is None:
        raise exceptions.ElementDoesNotExist(f"Contact with id '{contact_person_id}', not found.")

    if bioinformatician_contact_id is not None:
        if (bioinformatician_contact := self._session.get(models.Contact, bioinformatician_contact_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Contact with id '{bioinformatician_contact_id}', not found.")
    else:
        bioinformatician_contact = None
        
    seq_request = models.SeqRequest(
        name=name.strip(),
        description=description.strip() if description else None,
        requestor_id=requestor_id,
        sequencing_type_id=seq_type.id,
        num_cycles_read_1=num_cycles_read_1,
        num_cycles_index_1=num_cycles_index_1,
        num_cycles_index_2=num_cycles_index_2,
        num_cycles_read_2=num_cycles_read_2,
        read_length=read_length,
        num_lanes=num_lanes,
        special_requirements=special_requirements,
        billing_contact_id=billing_contact_id,
        contact_person_id=contact_person_id,
        bioinformatician_contact_id=bioinformatician_contact_id,
        status_id=SeqRequestStatus.DRAFT.id,
        data_delivery_mode_id=data_delivery_mode.id,
        organization_name=organization_name.strip(),
        organization_department=organization_department.strip() if organization_department else None,
        organization_address=organization_address.strip(),
        billing_code=billing_code.strip() if billing_code else None,
    )

    requestor.num_seq_requests += 1

    seq_request.delivery_email_links.append(models.SeqRequestDeliveryEmailLink(
        email=requestor.email,
        status_id=DeliveryStatus.PENDING.id,
    ))
    self._session.add(seq_request)
    self._session.add(requestor)
    self._session.commit()
    self._session.refresh(seq_request)

    if bioinformatician_contact is not None:
        seq_request.delivery_email_links.append(models.SeqRequestDeliveryEmailLink(
            email=bioinformatician_contact.email,
            status_id=DeliveryStatus.PENDING.id,
        ))
        self._session.add(seq_request)
        self._session.commit()
        self._session.refresh(seq_request)

    if not persist_session:
        self.close_session()

    return seq_request


def get_seq_request(
    self, seq_request_id: int,
) -> models.SeqRequest:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    seq_request = self._session.get(models.SeqRequest, seq_request_id)

    if not persist_session:
        self.close_session()
    return seq_request


def get_seq_requests(
    self,
    with_statuses: Optional[list[SeqRequestStatusEnum]] = None,
    show_drafts: bool = True,
    sample_id: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    user_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
) -> tuple[list[models.SeqRequest], int]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.SeqRequest)

    if user_id is not None:
        query = query.where(
            models.SeqRequest.requestor_id == user_id
        )

    if with_statuses is not None:
        status_ids = [status.id for status in with_statuses]
        query = query.where(
            models.SeqRequest.status_id.in_(status_ids)  # type: ignore
        )

    if not show_drafts:
        query = query.where(
            models.SeqRequest.status_id != SeqRequestStatus.DRAFT.id
        )

    if sample_id is not None:
        query = query.join(
            models.Library,
            models.Library.seq_request_id == models.SeqRequest.id,
        ).join(
            models.SampleLibraryLink,
            and_(
                models.SampleLibraryLink.library_id == models.Library.id,
                models.SampleLibraryLink.sample_id == sample_id
            )
        )

    if sort_by is not None:
        attr = getattr(models.SeqRequest, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr.nullslast())

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    seq_requests = query.all()

    if not persist_session:
        self.close_session()

    return seq_requests, n_pages


def get_num_seq_requests(
    self, user_id: Optional[int] = None,
    with_statuses: Optional[list[SeqRequestStatusEnum]] = None,
) -> int:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.SeqRequest)

    if user_id is not None:
        query = query.where(
            models.SeqRequest.requestor_id == user_id
        )

    if with_statuses is not None:
        status_ids = [status.id for status in with_statuses]
        query = query.where(
            models.SeqRequest.status_id.in_(status_ids)  # type: ignore
        )

    num_seq_requests = query.count()

    if not persist_session:
        self.close_session()
    return num_seq_requests


def submit_seq_request(
    self, seq_request_id: int,
    commit: bool = True
) -> models.SeqRequest:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request}', not found.")

    seq_request.status_id = SeqRequestStatus.SUBMITTED.id
    seq_request.submitted_timestamp_utc = datetime.now()
    for library in seq_request.libraries:
        if library.status == LibraryStatus.DRAFT:
            library.status_id = LibraryStatus.SUBMITTED.id
        self._session.add(library)

    for pool in seq_request.pools:
        pool.status_id = PoolStatus.SUBMITTED.id
        self._session.add(pool)

    if commit:
        self._session.commit()
        self._session.refresh(seq_request)

    if not persist_session:
        self.close_session()

    return seq_request


def update_seq_request(
    self, seq_request: models.SeqRequest,
    commit: bool = True
) -> models.SeqRequest:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    self._session.add(seq_request)

    if commit:
        self._session.commit()
        self._session.refresh(seq_request)
        self._session.refresh(seq_request.billing_contact)
        self._session.refresh(seq_request.contact_person)
        if seq_request.bioinformatician_contact_id is not None:
            self._session.refresh(seq_request.bioinformatician_contact)

    if not persist_session:
        self.close_session()

    return seq_request


def delete_seq_request(
    self, seq_request_id: int,
    commit: bool = True
) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    seq_request = self._session.get(models.SeqRequest, seq_request_id)
    if not seq_request:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")

    libraries = seq_request.libraries
    
    for library in libraries:
        for link in library.sample_links:
            link.sample.num_libraries -= 1
            self._session.add(link.sample)
            if link.cmo is not None:
                self._session.delete(link.cmo)
            self._session.delete(link)

        if library.pool is not None:
            library.pool.num_libraries -= 1
            self._session.add(library.pool)
        self._session.delete(library)

    for pool in seq_request.pools:
        self._session.delete(pool)

    seq_request.requestor.num_seq_requests -= 1
    self._session.add(seq_request.requestor)

    self._session.delete(seq_request)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def query_seq_requests(
    self, word: str,
    user_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT,
) -> list[models.SeqRequest]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.SeqRequest)

    if user_id is not None:
        query = query.where(
            models.SeqRequest.requestor_id == user_id
        )

    query = query.order_by(
        sa.func.similarity(models.SeqRequest.name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    seq_requests = query.all()

    if not persist_session:
        self.close_session()
    return seq_requests


def add_file_to_seq_request(
    self, seq_request_id: int, file_id: int
) -> models.SeqRequest:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")

    if (file := self._session.get(models.File, file_id)) is None:
        raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
    
    if file.type == FileType.SEQ_AUTH_FORM:
        if seq_request.seq_auth_form_file_id is not None:
            raise exceptions.LinkAlreadyExists("SeqRequest already has a Seq Auth Form file linked.")
        seq_request.seq_auth_form_file_id = file_id
        self._session.add(seq_request)

    seq_request.files.append(file)

    self._session.commit()
    self._session.refresh(seq_request)

    if not persist_session:
        self.close_session()

    return seq_request


def remove_comment_from_seq_request(self, seq_request_id: int, comment_id: int, commit: bool = True) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")

    if (comment := self._session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id '{comment_id}', not found.")
    
    seq_request.comments.remove(comment)
    self._session.add(seq_request)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()
    return None


def remove_file_from_seq_request(self, seq_request_id: int, file_id: int, commit: bool = True) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")

    if (file := self._session.get(models.File, file_id)) is None:
        raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
    
    seq_request.files.remove(file)
    
    comments = self._session.query(models.Comment).where(
        models.Comment.file_id == file_id
    ).all()

    for comment in comments:
        self.remove_comment_from_seq_request(seq_request_id, comment.id, commit=False)

    self._session.add(seq_request)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()
    return None


def add_seq_request_share_email(self, seq_request_id: int, email: str) -> models.SeqRequest:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    seq_request: models.SeqRequest
    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
    
    if self._session.query(models.SeqRequestDeliveryEmailLink).where(
        models.SeqRequestDeliveryEmailLink.seq_request_id == seq_request_id,
        models.SeqRequestDeliveryEmailLink.email == email
    ).first() is not None:
        raise exceptions.LinkAlreadyExists(f"SeqRequest with id '{seq_request_id}' already has a share link with email '{email}'.")

    seq_request.delivery_email_links.append(models.SeqRequestDeliveryEmailLink(
        email=email, status_id=DeliveryStatus.PENDING.id
    ))

    self._session.add(seq_request)
    self._session.commit()
    self._session.refresh(seq_request)

    if not persist_session:
        self.close_session()

    return seq_request


def remove_seq_request_share_email(self, seq_request_id: int, email: str) -> models.SeqRequest:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    seq_request: models.SeqRequest
    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
    
    if (delivery_link := self._session.query(models.SeqRequestDeliveryEmailLink).where(
        models.SeqRequestDeliveryEmailLink.seq_request_id == seq_request_id,
        models.SeqRequestDeliveryEmailLink.email == email
    ).first()) is None:
        raise exceptions.ElementDoesNotExist(f"Share link with '{email}', not found.")

    seq_request.delivery_email_links.remove(delivery_link)
    self._session.delete(delivery_link)
    self._session.add(seq_request)
    self._session.commit()
    self._session.refresh(seq_request)

    if not persist_session:
        self.close_session()
    return seq_request


def process_seq_request(self, seq_request_id: int, status: SeqRequestStatusEnum) -> models.SeqRequest:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")

    seq_request.status_id = status.id
    
    if status == SeqRequestStatus.ACCEPTED:
        pool_status = PoolStatus.ACCEPTED
        library_status = LibraryStatus.ACCEPTED
    elif status == SeqRequestStatus.DRAFT:
        pool_status = PoolStatus.DRAFT
        library_status = LibraryStatus.DRAFT
    elif status == SeqRequestStatus.REJECTED:
        pool_status = PoolStatus.REJECTED
        library_status = LibraryStatus.REJECTED
    else:
        raise TypeError(f"Cannot process request to '{status}'.")

    for pool in seq_request.pools:
        pool.status_id = pool_status.id
        self._session.add(pool)

    for library in seq_request.libraries:
        library.status_id = library_status.id
        self._session.add(library)

    self._session.add(seq_request)
    self._session.commit()
    self._session.refresh(seq_request)

    if not persist_session:
        self.close_session()

    return seq_request