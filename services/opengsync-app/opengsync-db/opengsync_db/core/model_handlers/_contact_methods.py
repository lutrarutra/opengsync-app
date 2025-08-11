from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models
from .. import exceptions


def create_contact(
    self: "DBHandler", name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    flush: bool = True
) -> models.Contact:

    if not (persist_session := self._session is not None):
        self.open_session()

    contact = models.Contact(
        name=name.strip(),
        email=email.strip() if email else None,
        phone=phone.strip() if phone else None,
        address=address.strip() if address else None
    )

    self.session.add(contact)
    if flush:
        self.flush()

    if not persist_session:
        self.close_session()

    return contact


def update_contact(
    self: "DBHandler",
    contact_id: int,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
) -> models.Contact:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    if (contact := self.session.get(models.Contact, contact_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Contact with ID {contact_id} does not exist")
    
    if name is not None:
        contact.name = name

    if email is not None:
        contact.email = email

    if phone is not None:
        contact.phone = phone

    if address is not None:
        contact.address = address

    if not persist_session:
        self.close_session()

    return contact
