from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

from limbless_db.categories import BarcodeType, BarcodeTypeEnum

if TYPE_CHECKING:
    from .Adapter import Adapter


class Barcode(Base):
    __tablename__ = "barcode"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, default=None)

    sequence: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(sa.String(16), nullable=True)
    
    adapter: Mapped["Adapter"] = relationship("Adapter", lazy="select", overlaps="barcodes_i7,barcodes_i5")
    adapter_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("adapter.id"), nullable=False)
    
    index_kit_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("index_kit.id"), nullable=False)
    type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    @property
    def type(self) -> BarcodeTypeEnum:
        return BarcodeType.get(self.type_id)

    def __str__(self) -> str:
        return f"Barcode({self.name}, {self.sequence}, {self.type})"
    
    def __repr__(self) -> str:
        return str(self)
    