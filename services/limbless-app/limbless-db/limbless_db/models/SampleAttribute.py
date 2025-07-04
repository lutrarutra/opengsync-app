import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ..categories import AttributeType, AttributeTypeEnum
from .Base import Base


class SampleAttribute(Base):
    __tablename__ = "sample_attribute"

    sample_id: Mapped[int] = mapped_column(sa.ForeignKey("sample.id"), nullable=False, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, primary_key=True, index=True)
    value: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    @property
    def type(self) -> AttributeTypeEnum:
        return AttributeType.get(self.type_id)