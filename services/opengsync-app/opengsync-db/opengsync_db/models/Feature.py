
from typing import TYPE_CHECKING, ClassVar, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from ..categories import FeatureType, FeatureTypeEnum

if TYPE_CHECKING:
    from .FeatureKit import FeatureKit


class Feature(Base):
    __tablename__ = "feature"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    sequence: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True)
    pattern: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    read: Mapped[str] = mapped_column(sa.String(8), nullable=False)
    target_name: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True, index=True)
    target_id: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True, index=True)

    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    feature_kit_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("feature_kit.id"), nullable=True)
    feature_kit: Mapped[Optional["FeatureKit"]] = relationship("FeatureKit", back_populates="features", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "target_name", "target_id", "feature_kit_id"]

    @property
    def type(self) -> FeatureTypeEnum:
        return FeatureType.get(self.type_id)
    
    def search_name(self) -> str:
        return self.name
    
    def search_value(self) -> int:
        return self.id
    
    def search_description(self) -> str | None:
        return self.type.name
    
    def __repr__(self) -> str:
        return f"Feature(id={self.id}, name={self.name}, sequence={self.sequence}, pattern={self.pattern}, read={self.read}, feature_kit_id={self.feature_kit_id})"

    __table_args__ = (
        sa.Index(
            "trgm_feature_name_idx", sa.func.lower(name),
            postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}
        ),
        sa.Index(
            "trgm_feature_target_id_idx", sa.func.lower(target_id),
            postgresql_using="gin", postgresql_ops={"target_id": "gin_trgm_ops"}
        ),
        sa.Index(
            "trgm_feature_target_name_idx", sa.func.lower(target_name),
            postgresql_using="gin", postgresql_ops={"target_name": "gin_trgm_ops"}
        )
    )