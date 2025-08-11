from typing import ClassVar, Optional, TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableDict

from ..categories import RunStatus, RunStatusEnum, ReadType, ReadTypeEnum
from ..core import units
from .Base import Base

if TYPE_CHECKING:
    from .Experiment import Experiment


class SeqRun(Base):
    __tablename__ = "seq_run"
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

    _quantities: Mapped[Optional[dict[str, dict[str, Any]]]] = mapped_column(MutableDict.as_mutable(JSONB), nullable=True, default=None, name="quantities")

    experiment: Mapped[Optional["Experiment"]] = relationship("Experiment", lazy="joined", primaryjoin="SeqRun.experiment_name == Experiment.name", foreign_keys=experiment_name, cascade="save-update")

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
    def quantities(self) -> dict[str, units.Quantity]:
        if self._quantities is None:
            return {}
        return {key: units.from_dict(q) for key, q in self._quantities.items()}

    def get_quantity(self, key: str) -> units.Quantity | None:
        if self._quantities is None or (data := self._quantities.get(key)) is None:
            return None
        return units.from_dict(data)
            
    def set_quantity(self, key: str, value: units.Quantity) -> None:
        if self._quantities is None:
            self._quantities = {}
        self._quantities[key] = value.to_dict()

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
    
    def __str__(self) -> str:
        return f"SeqRun(id={self.id}, experiment_name={self.experiment_name}, status={self.status}, read_type={self.read_type})"

    def __repr__(self) -> str:
        return self.__str__()

    __table_args__ = (
        sa.Index(
            "trgm_seq_run_experiment_name_idx",
            sa.text("lower(experiment_name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )