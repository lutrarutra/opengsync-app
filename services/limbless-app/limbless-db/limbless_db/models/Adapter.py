from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .Barcode import Barcode


class Adapter(Base):
    __tablename__ = "adapter"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True)
    index_kit_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("indexkit.id"), nullable=True)

    barcode_1_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("barcode.id"), nullable=True, default=None)
    barcode_1: Mapped[Optional["Barcode"]] = relationship("Barcode", lazy="joined", primaryjoin="Adapter.barcode_1_id == Barcode.id")

    barcode_2_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("barcode.id"), nullable=True, default=None)
    barcode_2: Mapped[Optional["Barcode"]] = relationship("Barcode", lazy="joined", primaryjoin="Adapter.barcode_2_id == Barcode.id")

    barcode_3_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("barcode.id"), nullable=True, default=None)
    barcode_3: Mapped[Optional["Barcode"]] = relationship("Barcode", lazy="joined", primaryjoin="Adapter.barcode_3_id == Barcode.id")

    barcode_4_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("barcode.id"), nullable=True, default=None)
    barcode_4: Mapped[Optional["Barcode"]] = relationship("Barcode", lazy="joined", primaryjoin="Adapter.barcode_4_id == Barcode.id")

    sortable_fields: ClassVar[list[str]] = ["id", "name"]

    def name_class(self) -> str:
        return "latin"
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return None
    
    def __str__(self) -> str:
        return f"Adapter({self.name})"
        
