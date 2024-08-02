from typing import TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..categories import IndexType, IndexTypeEnum
from .Base import Base

if TYPE_CHECKING:
    from .Barcode import Barcode
    from .Adapter import Adapter


class IndexKit(Base):
    __tablename__ = "index_kit"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True, unique=True)

    type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    
    barcodes: Mapped[list["Barcode"]] = relationship("Barcode", back_populates="index_kit", lazy="select")
    adapters: Mapped[list["Adapter"]] = relationship("Adapter", back_populates="index_kit", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "name"]

    @property
    def type(self) -> IndexTypeEnum:
        return IndexType.get(self.type_id)

    def __str__(self):
        return f"IndexKit('{self.name}')"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> str | None:
        return self.type.name
