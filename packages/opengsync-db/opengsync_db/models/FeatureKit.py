from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Kit import Kit
from ..categories import FeatureType, FeatureType, KitType
from ..core.EnumColumn import EnumColumn

if TYPE_CHECKING:
    from .Feature import Feature


class FeatureKit(Kit):
    __tablename__ = "feature_kit"
    id: Mapped[int] = mapped_column(sa.ForeignKey("kit.id"), primary_key=True)
    type: Mapped[FeatureType] = mapped_column(EnumColumn[FeatureType](FeatureType), nullable=False, name="type_id", key="type")

    features: Mapped[list["Feature"]] = relationship("Feature", back_populates="feature_kit", lazy="select")

    __mapper_args__ = {"polymorphic_identity": KitType.FEATURE_KIT.id}

    def __str__(self):
        return f"FeatureKit('{self.id}', '{self.name}')"
