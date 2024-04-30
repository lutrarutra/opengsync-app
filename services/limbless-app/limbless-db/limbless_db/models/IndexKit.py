from typing import TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .Barcode import Barcode


class IndexKit(Base):
    __tablename__ = "indexkit"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True, unique=True)

    num_indices_per_adapter: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    barcodes: Mapped[list["Barcode"]] = relationship("Barcode", back_populates="index_kit", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "name"]

    def __str__(self):
        return f"IndexKit('{self.name}')"
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
