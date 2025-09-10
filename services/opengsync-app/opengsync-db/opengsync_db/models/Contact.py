from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .Base import Base


class Contact(Base):
    __tablename__ = "contact"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(sa.String(128), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(sa.String(1024), nullable=True)

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Contact(id={self.id}, name={self.name}, email={self.email}, phone={self.phone}, address={self.address})"
