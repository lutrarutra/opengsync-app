import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..categories import ServiceType, ServiceType
from ..core.EnumColumn import EnumColumn


from .Base import Base
from . import links


class Protocol(Base):
    __tablename__ = "protocol"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(512), nullable=False, index=True, unique=True)
    read_structure: Mapped[str | None] = mapped_column(sa.String(256), nullable=True, default=None)

    service_type: Mapped[ServiceType] = mapped_column(EnumColumn[ServiceType](ServiceType), nullable=False, name="service_type_id", key="service_type")
    
    kit_links: Mapped[list[links.ProtocolKitLink]] = relationship(
        links.ProtocolKitLink, lazy="select", cascade="save-update, merge, delete, delete-orphan",
        order_by="links.ProtocolKitLink.combination_num",
    )

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return f"{self.name}"
    
    def __str__(self):
        return f"Protocol('{self.name}', '{self.service_type.name}')"
    
    def __repr__(self) -> str:
        return self.__str__()

    __table_args__ = (
        sa.Index(
            "trgm_protocol_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )