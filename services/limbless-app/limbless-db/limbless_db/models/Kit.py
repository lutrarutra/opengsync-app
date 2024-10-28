from typing import ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ..categories import KitType, KitTypeEnum


from .Base import Base


class Kit(Base):
    __tablename__ = "kit"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False, index=True, unique=False)
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