import sqlalchemy as sa

from ..models import Contact


def create(
    name: str,
    email: str | None = None,
    phone: str | None = None,
    address: str | None = None,
) -> Contact:
    return Contact(
        name=name.strip(),
        email=email.strip() if email else None,
        phone=phone.strip() if phone else None,
        address=address.strip() if address else None
    )


def select(
    id: int | None = None,
    statement: sa.Select[tuple[Contact]] = sa.select(Contact),
) -> sa.Select[tuple[Contact]]:
    if id is not None:
        statement = statement.where(Contact.id == id)
    return statement