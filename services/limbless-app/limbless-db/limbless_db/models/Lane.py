from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

from .Links import LanePoolLink

if TYPE_CHECKING:
    from .Experiment import Experiment
    from .Pool import Pool


class Lane(Base):
    __tablename__ = "lane"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    phi_x: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)

    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiment.id"), nullable=False)
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="lanes", lazy="select")

    pools: Mapped[list["Pool"]] = relationship("Pool", secondary=LanePoolLink, back_populates="lanes", lazy="select",)

    sortable_fields: ClassVar[list[str]] = ["id", "number", "experiment_id", "phi_x"]

    def __str__(self):
        return f"Lane(id={self.id}, number={self.number})"
