from typing import Optional, ClassVar, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..categories import BarcodeType
from .Base import Base

if TYPE_CHECKING:
    from .Barcode import Barcode
    from .IndexKit import IndexKit


class Adapter(Base):
    __tablename__ = "adapter"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True)
    plate_well: Mapped[Optional[str]] = mapped_column(sa.String(4), nullable=True)

    barcodes_i7: Mapped[list["Barcode"]] = relationship("Barcode", lazy="select", cascade="all, save-update, merge, delete", primaryjoin=f"and_(Adapter.id == Barcode.adapter_id, Barcode.type_id == {BarcodeType.INDEX_I7.id})", overlaps="barcodes_i5")
    barcodes_i5: Mapped[list["Barcode"]] = relationship("Barcode", lazy="select", cascade="all, save-update, merge, delete", primaryjoin=f"and_(Adapter.id == Barcode.adapter_id, Barcode.type_id == {BarcodeType.INDEX_I5.id})", overlaps="barcodes_i7")
    
    index_kit_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("index_kit.id"), nullable=False)
    index_kit: Mapped["IndexKit"] = relationship("IndexKit", back_populates="adapters", lazy="select")

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
        
