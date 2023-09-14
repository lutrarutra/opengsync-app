from typing import Optional

from ... import models
from .. import exceptions


def create_seq_request(
    self, name: str,
    description: Optional[str],
    requestor_id: int,
    person_contact_id: int,
    billing_contact_id: int,
    commit: bool = True
) -> models.SeqRequest:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.User, requestor_id) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{requestor_id}', not found.")

    if self._session.get(models.User, billing_contact_id) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{billing_contact_id}', not found.")

    seq_request = models.SeqRequest(
        name=name,
        description=description,
        requestor_id=requestor_id,
        billing_contact_id=billing_contact_id,
        person_contact_id=person_contact_id
    )

    self._session.add(seq_request)
    if commit:
        self._session.commit()
        self._session.refresh(seq_request)

    if not persist_session:
        self.close_session()
    return seq_request
