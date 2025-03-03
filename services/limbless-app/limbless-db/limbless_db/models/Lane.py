from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from . import links


if TYPE_CHECKING:
    from .Experiment import Experiment
    from .File import File


class Lane(Base):
    __tablename__ = "lane"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    
    phi_x: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    avg_fragment_size: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, default=None)
    original_qubit_concentration: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    sequencing_qubit_concentration: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    total_volume_ul: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    library_volume_ul: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    target_molarity: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)

    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiment.id"), nullable=False)
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="lanes", lazy="select")

    ba_report_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("file.id"), nullable=True, default=None)
    ba_report: Mapped[Optional["File"]] = relationship("File", lazy="select")

    pool_links: Mapped[list["links.LanePoolLink"]] = relationship(
        "links.LanePoolLink", back_populates="lane", lazy="select"
    )

    sortable_fields: ClassVar[list[str]] = ["id", "number", "experiment_id", "phi_x"]

    warning_min_molarity: ClassVar[float] = 1.0
    warning_max_molarity: ClassVar[float] = 5.0
    error_min_molarity: ClassVar[float] = 0.5
    error_max_molarity: ClassVar[float] = 10.0

    def is_qced(self) -> bool:
        return (
            self.avg_fragment_size is not None and
            self.original_qubit_concentration is not None
        )

    def is_loaded(self) -> bool:
        return (
            self.is_qced() and
            self.sequencing_qubit_concentration is not None and
            self.total_volume_ul is not None and
            self.library_volume_ul is not None and
            self.target_molarity is not None and
            self.phi_x is not None
        )

    @property
    def original_molarity(self) -> float | None:
        if self.original_qubit_concentration is None or self.avg_fragment_size is None:
            return None
        return self.original_qubit_concentration / (self.avg_fragment_size * 660) * 1_000_000
    
    @property
    def sequencing_molarity(self) -> float | None:
        if self.sequencing_qubit_concentration is None or self.avg_fragment_size is None:
            return None
        return self.sequencing_qubit_concentration / (self.avg_fragment_size * 660) * 1_000_000
    
    @property
    def qubit_concentration(self) -> float | None:
        if self.sequencing_qubit_concentration is not None:
            return self.sequencing_qubit_concentration
        return self.original_qubit_concentration
    
    @property
    def molarity(self) -> float | None:
        if self.sequencing_qubit_concentration is not None:
            return self.sequencing_molarity
        return self.original_molarity
    
    @property
    def molarity_color_class(self) -> str:
        if (molarity := self.molarity) is None:
            return ""
        
        if molarity < self.error_min_molarity or self.error_max_molarity < molarity:
            return "cemm-red"
        
        if molarity < self.warning_min_molarity or self.warning_max_molarity < molarity:
            return "cemm-yellow"
        
        return "cemm-green"
    
    @property
    def qubit_concentration_str(self) -> str:
        if (q := self.qubit_concentration) is None:
            return ""
        return f"{q:.2f}"
    
    @property
    def molarity_str(self) -> str:
        if (m := self.molarity) is None:
            return ""
        return f"{m:.2f}"

    def __str__(self) -> str:
        return f"Lane(id={self.id}, number={self.number})"
    
    def __repr__(self) -> str:
        return str(self)
