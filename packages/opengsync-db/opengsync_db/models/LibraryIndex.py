from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from ..categories import BarcodeOrientation, BarcodeOrientation, IndexType, IndexType

if TYPE_CHECKING:
    from .IndexKit import IndexKit


class LibraryIndex(Base):
    __tablename__ = "library_index"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, default=None)
    library_id: Mapped[int] = mapped_column(sa.ForeignKey("library.id"))

    index_kit_i7_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("index_kit.id"), nullable=True)
    index_kit_i7: Mapped[Optional["IndexKit"]] = relationship("IndexKit", lazy="select", foreign_keys=[index_kit_i7_id])

    index_kit_i5_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("index_kit.id"), nullable=True)
    index_kit_i5: Mapped[Optional["IndexKit"]] = relationship("IndexKit", lazy="select", foreign_keys=[index_kit_i5_id])

    name_i7: Mapped[Optional[str]] = mapped_column(sa.String(16), nullable=True)
    name_i5: Mapped[Optional[str]] = mapped_column(sa.String(16), nullable=True)
    sequence_i7: Mapped[str] = mapped_column(sa.String(32), nullable=True)
    sequence_i5: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)

    _orientation: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True, name="orientation")

    def __str__(self) -> str:
        return f"LibraryIndex({self.name_i7}: {self.sequence_i7}, {self.name_i5}: {self.sequence_i5})"
    
    def __repr__(self) -> str:
        return str(self)
    
    def is_kit_index(self) -> bool:
        # i7 must be always present for a kit index
        if self.index_kit_i7_id is None or not self.name_i7:
            return False
        
        # i5 is optional
        if not self.sequence_i5:
            return True
        
        # if dual index, kit i5 and name i5 must be present
        return self.index_kit_i5_id is not None and bool(self.name_i5)
    
    @property
    def type(self) -> IndexType:
        if self.sequence_i5 is None:
            return IndexType.SINGLE_INDEX_I7
        return IndexType.DUAL_INDEX
            
    @property
    def orientation(self) -> BarcodeOrientation | None:
        if self._orientation is None:
            return None
        return BarcodeOrientation.get(self._orientation)
    
    @orientation.setter
    def orientation(self, value: BarcodeOrientation | None) -> None:
        if value is None:
            self._orientation = None
        else:
            self._orientation = value.id
    