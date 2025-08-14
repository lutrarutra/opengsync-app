from typing import Optional

from ... import models
from ..DBBlueprint import DBBlueprint


class ContactBP(DBBlueprint):
    @DBBlueprint.transaction
    def create_contact(
        self, name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
        flush: bool = True
    ) -> models.Contact:

        contact = models.Contact(
            name=name.strip(),
            email=email.strip() if email else None,
            phone=phone.strip() if phone else None,
            address=address.strip() if address else None
        )

        self.db.session.add(contact)
        if flush:
            self.db.flush()

        return contact

    @DBBlueprint.transaction
    def update(self, contact: models.Contact):
        self.db.session.add(contact)
