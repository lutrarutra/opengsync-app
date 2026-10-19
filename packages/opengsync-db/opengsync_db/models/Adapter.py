from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..categories import BarcodeType
from .Base import Base

if TYPE_CHECKING:
    from .Barcode import Barcode
    from .IndexKit import IndexKit


class Adapter(Base):
    __tablename__ = "adapter"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    well: Mapped[Optional[str]] = mapped_column(sa.String(4), nullable=True)

    barcodes_i7: Mapped[list["Barcode"]] = relationship("Barcode", lazy="select", cascade="all, save-update, merge, delete", primaryjoin=f"and_(Adapter.id == Barcode.adapter_id, Barcode.type == {BarcodeType.INDEX_I7.id})", overlaps="barcodes_i5")
    barcodes_i5: Mapped[list["Barcode"]] = relationship("Barcode", lazy="select", cascade="all, save-update, merge, delete", primaryjoin=f"and_(Adapter.id == Barcode.adapter_id, Barcode.type == {BarcodeType.INDEX_I5.id})", overlaps="barcodes_i7")
    
    index_kit_id: Mapped[int] = mapped_column(sa.ForeignKey("index_kit.id"), nullable=False)
    index_kit: Mapped["IndexKit"] = relationship("IndexKit", back_populates="adapters", lazy="select")
    
    @hybrid_property
    def name(self) -> str | None:  # type: ignore[override]
        """Name of the first i7 barcode (what the adapter table shows as 'Name')."""
        return self.barcodes_i7[0].name if self.barcodes_i7 else None

    @name.expression
    def name(cls) -> sa.ScalarSelect[str | None]:
        from .Barcode import Barcode
        return sa.select(
            sa.func.min(Barcode.name)
        ).where(
            (Barcode.adapter_id == cls.id) & (Barcode.type == BarcodeType.INDEX_I7)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    def __str__(self) -> str:
        return f"Adapter({self.id}, '{self.well}')"
        
    def __repr__(self) -> str:
        return self.__str__()
