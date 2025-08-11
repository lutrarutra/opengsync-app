from typing import Optional, TYPE_CHECKING
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opengsync_db import models

from .Base import Base

if TYPE_CHECKING:
    from .Pool import Pool


class PoolDilution(Base):
    __tablename__ = "pool_dilution"
    id = mapped_column(sa.Integer, primary_key=True)

    identifier: Mapped[str] = mapped_column(sa.String(4), nullable=False)
    
    pool_id: Mapped[int] = mapped_column(sa.ForeignKey("pool.id"))
    pool: Mapped["Pool"] = relationship("Pool", back_populates="dilutions", lazy="joined")

    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    operator_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    operator: Mapped[models.User] = relationship("User", lazy="joined")

    qubit_concentration: Mapped[float] = mapped_column(sa.Float)
    volume_ul: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)

    def molarity(self, pool: models.Pool) -> float | None:
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
        return self.timestamp_utc

    def timestamp_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        return self.timestamp.strftime(fmt)
    
    def __str__(self) -> str:
        return f"PoolDilution({self.identifier}, {self.qubit_concentration:.2f})"
    
    def __repr__(self) -> str:
        return self.__str__()