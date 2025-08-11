from typing import ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ..categories import KitType, KitTypeEnum


from .Base import Base


class Kit(Base):
    __tablename__ = "kit"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False, index=True, unique=True)
    identifier: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True, unique=True)

    kit_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    
    sortable_fields: ClassVar[list[str]] = ["id", "name", "identifier", "kit_type_id"]

    __mapper_args__ = {
        "polymorphic_identity": KitType.LIBRARY_KIT.id,
        "polymorphic_on": "kit_type_id",
    }

    @property
    def kit_type(self) -> KitTypeEnum:
        return KitType.get(self.kit_type_id)
    
    @kit_type.setter
    def kit_type(self, value: KitTypeEnum):
        self.kit_type_id = value.id

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return f"{self.name} [{self.identifier}]"
    
    def search_description(self) -> str | None:
        return self.identifier
    
    def __str__(self):
        return f"Kit('{self.identifier}', '{self.name}', '{self.kit_type.name}')"
    
    def __repr__(self) -> str:
        return self.__str__()

    __table_args__ = (
        sa.Index(
            "trgm_kit_name_idx", sa.func.lower(name),
            postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}
        ),
        sa.Index(
            "trgm_kit_identifier_idx", sa.func.lower(identifier),
            postgresql_using="gin", postgresql_ops={"identifier": "gin_trgm_ops"}
        ),
        sa.Index(
            "trgm_kit_identifier_name_idx",
            sa.text("lower(identifier || ' ' || name) gin_trgm_ops"),
            postgresql_using="gin",
        )
    )