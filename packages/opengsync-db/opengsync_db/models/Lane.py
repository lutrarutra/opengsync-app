from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property

from .Base import Base
from . import links


if TYPE_CHECKING:
    from .Experiment import Experiment
    from .MediaFile import MediaFile


class Lane(Base):
    __tablename__ = "lane"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    
    phi_x: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    _avg_fragment_size: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, default=None, name="avg_fragment_size")
    _original_qubit_concentration: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None, name="original_qubit_concentration")
    sequencing_qubit_concentration: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    
    total_volume_ul: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    library_volume_ul: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    target_molarity: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)

    experiment_id: Mapped[int] = mapped_column(sa.ForeignKey("experiment.id"), nullable=False)
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="lanes", lazy="select")

    ba_report_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("media_file.id"), nullable=True, default=None)
    _ba_report: Mapped[Optional["MediaFile"]] = relationship("MediaFile", lazy="select", foreign_keys=[ba_report_id])

    pool_links: Mapped[list["links.LanePoolLink"]] = relationship(
        "LanePoolLink", back_populates="lane", lazy="select",
        cascade="save-update, merge, delete, delete-orphan",
    )

    sortable_fields: ClassVar[list[str]] = ["id", "number", "experiment_id", "phi_x"]

    warning_min_molarity: ClassVar[float] = 1.0
    warning_max_molarity: ClassVar[float] = 5.0
    error_min_molarity: ClassVar[float] = 0.5
    error_max_molarity: ClassVar[float] = 10.0

    def get_num_sequenced_reads(self) -> int:
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open")
        total_reads = 0
        for seq_quality in self.experiment.read_qualities:
            if seq_quality.lane == self.number:
                total_reads += seq_quality.num_reads
        return total_reads

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
    
    def get_loaded_reads(self) -> float:
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open for checklist")
        reads = 0.0
        for link in self.pool_links:
            if link.num_m_reads is not None:
                reads += link.num_m_reads
        return reads
    
    @hybrid_property
    def avg_fragment_size(self) -> int | None:  # type: ignore[override]  
        if self._avg_fragment_size is not None:
            return self._avg_fragment_size
        
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open to load avg_fragment_size")
        
        if len(self.pool_links) != 1:
            return None
        
        return self.pool_links[0].pool.avg_fragment_size
    
    @avg_fragment_size.setter
    def avg_fragment_size(self, value: int | None) -> None:  # type: ignore[override]
        self._avg_fragment_size = value
    
    @avg_fragment_size.expression
    def avg_fragment_size(cls) -> sa.ScalarSelect[int | None]:
        from .Pool import Pool
        
        count_subquery = sa.select(sa.func.count(links.LanePoolLink.pool_id)).where(
            links.LanePoolLink.lane_id == cls.id
        ).scalar_subquery()

        value_subquery = sa.select(Pool.avg_fragment_size).where(
            links.LanePoolLink.lane_id == cls.id,
            links.LanePoolLink.pool_id == Pool.id
        ).limit(1).scalar_subquery()

        return sa.case(
            (cls._avg_fragment_size != None, cls._avg_fragment_size),  # type: ignore[comparison-overlap]
            (count_subquery == 1, value_subquery),
            else_=None
        )   # type: ignore[arg-type]
    
    @hybrid_property
    def original_qubit_concentration(self) -> float | None:  # type: ignore[override]
        if self._original_qubit_concentration is not None:
            return self._original_qubit_concentration
        
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open to load original_qubit_concentration")
        
        if len(self.pool_links) != 1:
            return None
        
        return self.pool_links[0].pool.qubit_concentration
    
    @original_qubit_concentration.setter
    def original_qubit_concentration(self, value: float | None) -> None:  # type: ignore[override]
        self._original_qubit_concentration = value

    @original_qubit_concentration.expression
    def original_qubit_concentration(cls) -> sa.ScalarSelect[float | None]:
        from .Pool import Pool
        
        count_subquery = sa.select(sa.func.count(links.LanePoolLink.pool_id)).where(
            links.LanePoolLink.lane_id == cls.id
        ).scalar_subquery()

        value_subquery = sa.select(Pool.qubit_concentration).where(
            links.LanePoolLink.lane_id == cls.id,
            links.LanePoolLink.pool_id == Pool.id
        ).limit(1).scalar_subquery()

        return sa.case(
            (cls._original_qubit_concentration != None, cls._original_qubit_concentration),  # type: ignore[comparison-overlap]
            (count_subquery == 1, value_subquery),
            else_=None
        )  # type: ignore[arg-type]

    @property
    def original_molarity(self) -> float | None:
        if self.original_qubit_concentration is None or self.avg_fragment_size is None:
            return None
        return self.original_qubit_concentration / (self.avg_fragment_size * 660) * 1_000_000
    
    @property
    def qubit_concentration(self) -> float | None:
        if self.sequencing_qubit_concentration is not None:
            return self.sequencing_qubit_concentration
        return self.original_qubit_concentration
    
    @hybrid_property
    def lane_molarity(self) -> float | None:  # type: ignore[override]
        if self.original_qubit_concentration is None or self.avg_fragment_size is None:
            return None
        return self.original_qubit_concentration / (self.avg_fragment_size * 660) * 1_000_000
    
    @lane_molarity.expression
    def lane_molarity(self) -> sa.ColumnElement[float | None]:
        return sa.case(
            (
                sa.and_(
                    Lane.original_qubit_concentration.is_not(None),
                    Lane.avg_fragment_size.is_not(None)
                ),
                sa.cast(Lane.original_qubit_concentration, sa.Float) / (sa.cast(Lane.avg_fragment_size, sa.Float) * 660) * 1_000_000
            ),
            else_=None
        )

    @hybrid_property
    def sequencing_molarity(self) -> float | None:  # type: ignore[override]
        if self.sequencing_qubit_concentration is None or self.avg_fragment_size is None:
            return None
        return self.sequencing_qubit_concentration / (self.avg_fragment_size * 660) * 1_000_000

    @sequencing_molarity.expression
    def sequencing_molarity(self) -> sa.ColumnElement[float | None]:
        return sa.case(
            (
                sa.and_(
                    Lane.sequencing_qubit_concentration.is_not(None),
                    Lane._avg_fragment_size.is_not(None)
                ),
                sa.cast(Lane.sequencing_qubit_concentration, sa.Float) / (sa.cast(Lane.avg_fragment_size, sa.Float) * 660) * 1_000_000
            ),
            else_=None
        )

    @hybrid_property
    def molarity(self) -> float | None: # type: ignore[override]
        if self.sequencing_qubit_concentration is not None:
            return self.sequencing_molarity
        return self.original_molarity
    
    @molarity.expression
    def molarity(self) -> sa.ScalarSelect[float | None]:
        return sa.case(
            (Lane.sequencing_qubit_concentration.is_not(None), Lane.sequencing_molarity),
            else_=Lane.original_molarity
        ) # type: ignore[arg-type]
    
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
    def ba_report(self) -> "MediaFile | None":
        if self._ba_report is not None:
            return self._ba_report
        
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open to load ba_report")
        
        if len(self.pool_links) != 1:
            return None
        
        return self.pool_links[0].pool.ba_report
    
    @property
    def molarity_str(self) -> str:
        if (m := self.molarity) is None:
            return ""
        return f"{m:.2f}"

    def __str__(self) -> str:
        return f"Lane(id={self.id}, number={self.number})"
    
    def __repr__(self) -> str:
        return str(self)

    def m_reads_planned(self) -> float:
        reads = 0.0
        for link in self.pool_links:
            if link.num_m_reads is not None:
                reads += link.num_m_reads
        return reads