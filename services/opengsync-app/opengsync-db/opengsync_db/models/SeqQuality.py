from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .Library import Library
    from .Experiment import Experiment


class SeqQuality(Base):
    __tablename__ = "seq_quality"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, nullable=False, primary_key=True)
    lane: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    
    num_reads: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)

    qc: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSONB), nullable=True, default=None)

    # if library_id is None, it's undetermined reads
    library_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("library.id"), nullable=True)
    library: Mapped[Optional["Library"]] = relationship("Library", back_populates="read_qualities", lazy="select")

    experiment_id: Mapped[int] = mapped_column(sa.ForeignKey("experiment.id"), nullable=False)
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="read_qualities", lazy="select")