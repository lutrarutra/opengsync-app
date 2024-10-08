from typing import ClassVar, Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

from ..categories import RunStatus, RunStatusEnum, ReadType, ReadTypeEnum

if TYPE_CHECKING:
    from .Experiment import Experiment


class SeqRun(Base):
    __tablename__ = "seqrun"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    
    experiment_name: Mapped[str] = mapped_column(sa.String(16), nullable=False, unique=True, index=True)
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    instrument_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    run_folder: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    flowcell_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    read_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    rta_version: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
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

    experiment: Mapped[Optional["Experiment"]] = relationship("Experiment", lazy="joined", primaryjoin="SeqRun.experiment_name == Experiment.name", foreign_keys=experiment_name)

    sortable_fields: ClassVar[list[str]] = ["id", "experiment_name", "status_id", "read_type_id"]

    @property
    def status(self) -> RunStatusEnum:
        return RunStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: RunStatusEnum):
        self.status_id = value.id
    
    @property
    def read_type(self) -> ReadTypeEnum:
        return ReadType.get(self.read_type_id)
    
    @read_type.setter
    def read_type(self, value: ReadTypeEnum):
        self.read_type_id = value.id

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
