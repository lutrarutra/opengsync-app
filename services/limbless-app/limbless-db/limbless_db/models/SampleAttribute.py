import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ..categories import AttributeType, AttributeTypeEnum
from .Base import Base


class SampleAttribute(Base):
    __tablename__ = "sample_attribute"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    value: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    sample_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("sample.id"), nullable=False)

    @property
    def type(self) -> AttributeTypeEnum:
        return AttributeType.get(self.type_id)