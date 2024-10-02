from typing import ClassVar, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .Base import Base

from ..categories import RunStatus, RunStatusEnum, ReadType, ReadTypeEnum


class SeqRun(Base):
    __tablename__ = "seqrun"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    
    experiment_name: Mapped[str] = mapped_column(sa.String(16), nullable=False, unique=True, index=True)
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    instrument_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    run_folder: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    flowcell_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    read_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    rta_version: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    recipe_version: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    side: Mapped[Optional[str]] = mapped_column(sa.String(8), nullable=True)
    flowcell_mode: Mapped[Optional[str]] = mapped_column(sa.String(8), nullable=True)

    r1_cycles: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    r2_cycles: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    i1_cycles: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    i2_cycles: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)

    cluster_count_m: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    cluster_count_m_pf: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    error_rate: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    first_cycle_intensity: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    percent_aligned: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    percent_q30: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    percent_occupied: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    projected_yield: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    reads_m: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    reads_m_pf: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    yield_g: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)

    sortable_fields: ClassVar[list[str]] = ["id", "experiment_name", "status_id", "read_type_id"]

    @property
    def status(self) -> RunStatusEnum:
        return RunStatus.get(self.status_id)
    
    @property
    def read_type(self) -> ReadTypeEnum:
        return ReadType.get(self.read_type_id)
    
    @property
    def cycles_str(self) -> str:
        res = f"{self.r1_cycles}"
        
        if self.i1_cycles is not None:
            res += f"-{self.i1_cycles}"
        else:
            res += "-0"
        
        if self.i2_cycles is not None:
            res += f"-{self.i2_cycles}"
        else:
            res += "-0"

        if self.r2_cycles is not None:
            res += f"-{self.r2_cycles}"
        else:
            res += "-0"

        return res
