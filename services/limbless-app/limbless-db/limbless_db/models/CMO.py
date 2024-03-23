from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .Sample import Sample
    from .Library import Library


class CMO(Base):
    __tablename__ = "cmo"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    sequence: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    pattern: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    read: Mapped[str] = mapped_column(sa.String(8), nullable=False)

    sample_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("sample.id"), nullable=False)
    sample: Mapped["Sample"] = relationship(lazy="select")
    
    library_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("library.id"), nullable=False)
    library: Mapped["Library"] = relationship("Library", back_populates="cmos", lazy="select")

    def __str__(self) -> str:
        return f"CMO(id: {self.id}, sequence: {self.sequence}, pattern: {self.pattern}, read: {self.read}, sample_id: {self.sample_id}, library_id: {self.library_id})"