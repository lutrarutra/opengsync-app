from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .Pool import Pool
    from .Experiment import Experiment


class PoolDilution(Base):
    __tablename__ = "pool_dilution"
    id = mapped_column(sa.Integer, primary_key=True)
    
    pool_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("pool.id"))
    pool: Mapped["Pool"] = relationship("Pool", back_populates="dilutions", lazy="select")

    experiment_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("experiment.id"), nullable=True)
    experiment: Mapped[Optional["Experiment"]] = relationship("Experiment", lazy="select")

    qubit_concentration: Mapped[float] = mapped_column(sa.Float)
    volume_ul: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)