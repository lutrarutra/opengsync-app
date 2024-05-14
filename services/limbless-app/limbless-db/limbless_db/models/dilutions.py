from typing import Optional, TYPE_CHECKING
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from limbless_db import models

from .Base import Base
from .. import localize

if TYPE_CHECKING:
    from .Pool import Pool
    from .Experiment import Experiment


class PoolDilution(Base):
    __tablename__ = "pool_dilution"
    id = mapped_column(sa.Integer, primary_key=True)

    identifier: Mapped[str] = mapped_column(sa.String(4), nullable=False)
    
    pool_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("pool.id"))
    pool: Mapped["Pool"] = relationship("Pool", back_populates="dilutions", lazy="joined")

    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=sa.func.now())

    experiment_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("experiment.id"), nullable=True)
    experiment: Mapped[Optional["Experiment"]] = relationship("Experiment", lazy="select")

    operator_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    operator: Mapped[models.User] = relationship("User", lazy="joined")

    qubit_concentration: Mapped[float] = mapped_column(sa.Float)
    volume_ul: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)

    def molarity(self, pool: models.Pool) -> Optional[float]:
        if pool.avg_fragment_size is None:
            return None
        
        return self.qubit_concentration / (pool.avg_fragment_size * 660) * 1_000_000
    
    def molarity_str(self, pool: models.Pool) -> str:
        if (molarity := self.molarity(pool)) is None:
            return ""
        
        return f"{molarity:.2f}"
    
    def molarity_color_class(self, pool: models.Pool) -> str:
        if (molarity := self.molarity(pool)) is None:
            return ""
        
        if molarity < pool.error_min_molarity or pool.error_max_molarity < molarity:
            return "cemm-red"
        
        if molarity < pool.warning_min_molarity or pool.warning_max_molarity < molarity:
            return "cemm-yellow"
        
        return "cemm-green"
    
    @property
    def timestamp(self) -> datetime:
        return localize(self.timestamp_utc)

    def timestamp_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        return self.timestamp.strftime(fmt)
    
    def __str__(self) -> str:
        return f"PoolDilution({self.identifier}, {self.qubit_concentration:.2f})"
    
    def __repr__(self) -> str:
        return self.__str__()