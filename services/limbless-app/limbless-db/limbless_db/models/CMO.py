from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .Base import Base


class CMO(Base):
    __tablename__ = "cmo"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    sequence: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    pattern: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    read: Mapped[str] = mapped_column(sa.String(8), nullable=False)

    def __str__(self) -> str:
        return f"CMO(id: {self.id}, sequence: {self.sequence}, pattern: {self.pattern}, read: {self.read})"