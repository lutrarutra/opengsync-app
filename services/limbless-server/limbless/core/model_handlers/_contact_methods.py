from typing import Optional

from ... import models
from .. import exceptions


def create_contact(
    self, name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    commit: bool = True
) -> models.Contact:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    contact = models.Contact(
        name=name,
        email=email,
        phone=phone,
        address=address
    )

    self._session.add(contact)
    if commit:
        self._session.commit()
        self._session.refresh(contact)

    if not persist_session:
        self.close_session()

    return contact


def update_contact(
    self,
    contact_id: int,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    commit: bool = True
) -> models.Contact:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (contact := self._session.get(models.Contact, contact_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Contact with ID {contact_id} does not exist")
    
    if name is not None:
        contact.name = name

    if email is not None:
        contact.email = email

    if phone is not None:
        contact.phone = phone

    if address is not None:
        contact.address = address

    if commit:
        self._session.commit()
        self._session.refresh(contact)

    if not persist_session:
        self.close_session()

    return contact
