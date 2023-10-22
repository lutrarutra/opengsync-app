from typing import Optional

from ... import models
from ...categories import SeqRequestStatus
from .. import exceptions


def create_seq_request(
    self, name: str,
    description: Optional[str],
    requestor_id: int,
    person_contact_id: int,
    billing_contact_id: int,
    bioinformatician_contact_id: Optional[int] = None,
    library_person_contact_id: Optional[int] = None,
    commit: bool = True
) -> models.SeqRequest:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.User, requestor_id) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{requestor_id}', not found.")

    if self._session.get(models.Contact, billing_contact_id) is None:
        raise exceptions.ElementDoesNotExist(f"Contact with id '{billing_contact_id}', not found.")

    if self._session.get(models.Contact, person_contact_id) is None:
        raise exceptions.ElementDoesNotExist(f"Contact with id '{person_contact_id}', not found.")

    if bioinformatician_contact_id is not None:
        if self._session.get(models.Contact, bioinformatician_contact_id) is None:
            raise exceptions.ElementDoesNotExist(f"Contact with id '{bioinformatician_contact_id}', not found.")
        
    if library_person_contact_id is not None:
        if self._session.get(models.Contact, library_person_contact_id) is None:
            raise exceptions.ElementDoesNotExist(f"Contact with id '{library_person_contact_id}', not found.")

    seq_request = models.SeqRequest(
        name=name,
        description=description,
        requestor_id=requestor_id,
        billing_contact_id=billing_contact_id,
        person_contact_id=person_contact_id,
        bioinformatician_contact_id=bioinformatician_contact_id,
        library_person_contact_id=library_person_contact_id,
        status=SeqRequestStatus.DRAFT.value.id
    )

    self._session.add(seq_request)
    if commit:
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
    self, limit: Optional[int] = 20, offset: Optional[int] = None,
    with_statuses: Optional[list[SeqRequestStatus]] = None,
    sort_by: Optional[str] = None, reversed: bool = False,
    user_id: Optional[int] = None
) -> list[models.SeqRequest]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.SeqRequest)

    if user_id is not None:
        query = query.where(
            models.SeqRequest.requestor_id == user_id
        )

    if with_statuses is not None:
        status_ids = [status.value.id for status in with_statuses]
        query = query.where(
            models.SeqRequest.status.in_(status_ids)
        )

    if sort_by is not None:
        attr = getattr(models.SeqRequest, sort_by)
        if reversed:
            attr = attr.desc()
        query = query.order_by(attr)

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    seq_requests = query.all()

    if not persist_session:
        self.close_session()

    return seq_requests


def get_num_seq_requests(
    self, user_id: Optional[int] = None,
    with_statuses: Optional[list[SeqRequestStatus]] = None,
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
        status_ids = [status.value.id for status in with_statuses]
        query = query.where(
            models.SeqRequest.status.in_(status_ids)
        )

    num_seq_requests = query.count()

    if not persist_session:
        self.close_session()
    return num_seq_requests


def update_seq_request(
    self, seq_request_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[SeqRequestStatus] = None,
    commit: bool = True
) -> models.SeqRequest:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request}', not found.")

    if name is not None:
        seq_request.name = name

    if description is not None:
        seq_request.description = description

    if status is not None:
        seq_request.status = status.value.id

    if commit:
        self._session.commit()
        self._session.refresh(seq_request)

    if not persist_session:
        self.close_session()

    return seq_request


def delete_seq_request(
    self, sample_id: int,
    commit: bool = True
) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    seq_request = self._session.get(models.SeqRequest, sample_id)
    if not seq_request:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {sample_id} does not exist")

    self._session.delete(seq_request.contact_person)
    self._session.delete(seq_request.billing_contact)
    self._session.delete(seq_request)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()