from typing import TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..categories import IndexType, IndexTypeEnum, LabProtocol, LabProtocolEnum
from .Base import Base

if TYPE_CHECKING:
    from .Barcode import Barcode
    from .Adapter import Adapter


class IndexKit(Base):
    __tablename__ = "index_kit"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    identifier: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True, unique=True)
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False, index=True, unique=False)

    type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    supported_protocol_ids: Mapped[list[int]] = mapped_column(sa.ARRAY(sa.Integer), nullable=False)
    
    barcodes: Mapped[list["Barcode"]] = relationship("Barcode", back_populates="index_kit", lazy="select")
    adapters: Mapped[list["Adapter"]] = relationship("Adapter", back_populates="index_kit", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "identifier", "type_id"]

    @property
    def type(self) -> IndexTypeEnum:
        return IndexType.get(self.type_id)
    
    @property
    def supported_protocols(self) -> list[LabProtocolEnum]:
        return [LabProtocol.get(protocol_id) for protocol_id in self.supported_protocol_ids]
    
    def supported_protocols_str(self, sep: str = ", ") -> str:
        return sep.join([protocol.name for protocol in self.supported_protocols])

    def __str__(self):
        return f"IndexKit('{self.identifier}', '{self.name}')"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.identifier
    
    def search_description(self) -> str | None:
        return self.name
