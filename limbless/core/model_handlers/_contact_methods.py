from typing import Optional

from ... import models


def create_contact(
    self, name: str,
    organization: Optional[str],
    email: Optional[str],
    phone: Optional[str],
    address: Optional[str],
    billing_code: Optional[str],
    commit: bool = True
) -> models.Contact:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    contact = models.Contact(
        name=name,
        organization=organization,
        email=email,
        phone=phone,
        address=address,
        billing_code=billing_code
    )

    self._session.add(contact)
    if commit:
        self._session.commit()
        self._session.refresh(contact)

    if not persist_session:
        self.close_session()

    return contact
