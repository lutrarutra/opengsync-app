from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

from limbless_db.categories import BarcodeType, BarcodeTypeEnum

if TYPE_CHECKING:
    from .IndexKit import IndexKit


class Barcode(Base):
    __tablename__ = "barcode"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, default=None)

    sequence: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(16), nullable=False, index=True)
    well: Mapped[Optional[str]] = mapped_column(sa.String(4), nullable=True)

    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    adapter_id: Mapped[int] = mapped_column(sa.ForeignKey("adapter.id"), nullable=False)

    index_kit_id: Mapped[int] = mapped_column(sa.ForeignKey("index_kit.id"), nullable=False)
    index_kit: Mapped["IndexKit"] = relationship("IndexKit", back_populates="barcodes", lazy="select")

    @property
    def type(self) -> BarcodeTypeEnum:
        return BarcodeType.get(self.type_id)

    def __str__(self) -> str:
        return f"Barcode({self.name}, {self.sequence}, {self.type})"
    
    def __repr__(self) -> str:
        return str(self)
    
    @staticmethod
    def reverse_complement(seq: str) -> str:
        complement = {"A": "T", "T": "A", "C": "G", "G": "C"}
        return "".join(complement.get(base, base) for base in reversed(seq))