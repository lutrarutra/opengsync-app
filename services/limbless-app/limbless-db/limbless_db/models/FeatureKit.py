
from typing import TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

from ..categories import FeatureType, FeatureTypeEnum

if TYPE_CHECKING:
    from .Feature import Feature


class FeatureKit(Base):
    __tablename__ = "featurekit"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True, unique=True)

    type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    
    features: Mapped[list["Feature"]] = relationship("Feature", back_populates="feature_kit", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "name"]

    @property
    def type(self) -> FeatureTypeEnum:
        return FeatureType.get(self.type_id)

    def __str__(self):
        return f"FeatureKit('{self.id}', '{self.name}')"
