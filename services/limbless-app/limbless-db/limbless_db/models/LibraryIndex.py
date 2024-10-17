from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .IndexKit import IndexKit


class LibraryIndex(Base):
    __tablename__ = "library_index"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, default=None)
    library_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("library.id"))

    index_kit_i7_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("index_kit.id"), nullable=True)
    index_kit_i7: Mapped[Optional["IndexKit"]] = relationship("IndexKit", lazy="select", foreign_keys=[index_kit_i7_id])

    index_kit_i5_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("index_kit.id"), nullable=True)
    index_kit_i5: Mapped[Optional["IndexKit"]] = relationship("IndexKit", lazy="select", foreign_keys=[index_kit_i5_id])

    name_i7: Mapped[Optional[str]] = mapped_column(sa.String(16), nullable=True)
    name_i5: Mapped[Optional[str]] = mapped_column(sa.String(16), nullable=True)
    sequence_i7: Mapped[str] = mapped_column(sa.String(32), nullable=True)
    sequence_i5: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)

    def __str__(self) -> str:
        return f"LibraryIndex({self.name_i7}: {self.sequence_i7}, {self.name_i5}: {self.sequence_i5})"
    
    def __repr__(self) -> str:
        return str(self)
    