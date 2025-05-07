from typing import TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Kit import Kit
from ..categories import FeatureType, FeatureTypeEnum, KitType

if TYPE_CHECKING:
    from .Feature import Feature


class FeatureKit(Kit):
    __tablename__ = "feature_kit"
    id: Mapped[int] = mapped_column(sa.ForeignKey("kit.id"), primary_key=True)
    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    features: Mapped[list["Feature"]] = relationship("Feature", back_populates="feature_kit", lazy="select", cascade="all, save-update, merge, delete, delete-orphan")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "identifier", "type_id"]

    __mapper_args__ = {"polymorphic_identity": KitType.FEATURE_KIT.id}

    @property
    def type(self) -> FeatureTypeEnum:
        return FeatureType.get(self.type_id)
    
    @type.setter
    def type(self, value: FeatureTypeEnum):
        self.type_id = value.id

    def __str__(self):
        return f"FeatureKit('{self.id}', '{self.name}')"
