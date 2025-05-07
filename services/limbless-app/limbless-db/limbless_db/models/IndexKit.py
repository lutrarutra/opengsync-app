from typing import TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Kit import Kit
from ..categories import IndexType, IndexTypeEnum, LabProtocol, LabProtocolEnum, KitType


if TYPE_CHECKING:
    from .Barcode import Barcode
    from .Adapter import Adapter


class IndexKit(Kit):
    __tablename__ = "index_kit"
    id: Mapped[int] = mapped_column(sa.ForeignKey("kit.id"), primary_key=True)
    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    supported_protocol_ids: Mapped[list[int]] = mapped_column(sa.ARRAY(sa.Integer), nullable=False)
    
    barcodes: Mapped[list["Barcode"]] = relationship("Barcode", back_populates="index_kit", lazy="select", cascade="all, save-update, merge, delete, delete-orphan")
    adapters: Mapped[list["Adapter"]] = relationship("Adapter", back_populates="index_kit", lazy="select", cascade="all, save-update, merge, delete, delete-orphan")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "identifier", "type_id"]

    __mapper_args__ = {
        "polymorphic_identity": KitType.INDEX_KIT.id,
    }

    @property
    def type(self) -> IndexTypeEnum:
        return IndexType.get(self.type_id)
    
    @type.setter
    def type(self, value: IndexTypeEnum):
        self.type_id = value.id
    
    @property
    def supported_protocols(self) -> list[LabProtocolEnum]:
        return [LabProtocol.get(protocol_id) for protocol_id in self.supported_protocol_ids]
    
    def supported_protocols_str(self, sep: str = ", ") -> str:
        return sep.join([protocol.name for protocol in self.supported_protocols])

    def __str__(self):
        return f"IndexKit('{self.identifier}', '{self.name}')"
    
    def __repr__(self) -> str:
        return self.__str__()
