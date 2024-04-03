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
    qubit_concentration: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    total_volume_ul: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    library_volume_ul: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    avg_library_size: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, default=None)

    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiment.id"), nullable=False)
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="lanes", lazy="select")

    pools: Mapped[list["Pool"]] = relationship("Pool", secondary=LanePoolLink.__tablename__, back_populates="lanes", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "number", "experiment_id", "phi_x"]

    warning_min_molarity: ClassVar[float] = 1.0
    warning_max_molarity: ClassVar[float] = 5.0
    error_min_molarity: ClassVar[float] = 0.5
    error_max_molarity: ClassVar[float] = 10.0

    @property
    def molarity(self) -> Optional[float]:
        if self.qubit_concentration is None or self.avg_library_size is None:
            return None
        return self.qubit_concentration / (self.avg_library_size * 660) * 1_000_000

    def __str__(self):
        return f"Lane(id={self.id}, number={self.number})"
