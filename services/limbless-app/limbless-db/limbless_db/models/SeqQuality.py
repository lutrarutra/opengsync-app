from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .Library import Library
    from .Experiment import Experiment


class SeqQuality(Base):
    __tablename__ = "seqquality"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, nullable=False, primary_key=True)
    lane: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    
    num_lane_reads: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    num_library_reads: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    
    mean_quality_pf_r1: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    q30_perc_r1: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)

    mean_quality_pf_r2: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    q30_perc_r2: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)

    mean_quality_pf_i1: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    q30_perc_i1: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)

    mean_quality_pf_i2: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    q30_perc_i2: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)

    library_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("library.id"), nullable=True)
    library: Mapped[Optional["Library"]] = relationship("Library", back_populates="read_qualities", lazy="select")

    experiment_id: Mapped[int] = mapped_column(sa.ForeignKey("experiment.id"), nullable=False)
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="read_qualities", lazy="select")