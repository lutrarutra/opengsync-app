from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

from ..categories import BarcodeType, BarcodeTypeEnum

if TYPE_CHECKING:
    from .IndexKit import IndexKit


class Barcode(Base):
    __tablename__ = "barcode"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    sequence: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    adapter: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True, index=True)
    
    index_kit_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("indexkit.id"), nullable=True)
    index_kit: Mapped[Optional["IndexKit"]] = relationship("IndexKit", back_populates="barcodes", lazy="select",)

    type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    sortable_fields: ClassVar[list[str]] = ["id", "sequence", "type", "adapter_id", "index_kit_id"]

    def __str__(self):
        return f"Barcode('{self.sequence}', {self.type})"
    
    @property
    def type(self) -> BarcodeTypeEnum:
        return BarcodeType.get(self.type_id)
    
    @staticmethod
    def reverse_complement(sequence: str) -> str:
        return "".join([{"A": "T", "T": "A", "G": "C", "C": "G"}[base] for base in sequence[::-1]])
