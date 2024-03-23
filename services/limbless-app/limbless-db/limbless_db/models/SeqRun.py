from typing import ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .Base import Base

from ..categories import ExperimentStatus, ExperimentStatusEnum, ReadType, ReadTypeEnum


class SeqRun(Base):
    __tablename__ = "seqrun"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    
    experiment_name: Mapped[str] = mapped_column(sa.String(32), nullable=False, unique=True, index=True)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    run_folder: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    flowcell_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    read_type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    rta_version: Mapped[str] = mapped_column(sa.String(8), nullable=False)
    recipe_version: Mapped[str] = mapped_column(sa.String(8), nullable=False)
    side: Mapped[str] = mapped_column(sa.String(8), nullable=False)
    flowcell_mode: Mapped[str] = mapped_column(sa.String(8), nullable=False)

    r1_cycles: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    r2_cycles: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    i1_cycles: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    i2_cycles: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    sortable_fields: ClassVar[list[str]] = ["id", "experiment_name", "status_id", "read_type_id"]

    @property
    def status(self) -> ExperimentStatusEnum:
        return ExperimentStatus.get(self.status_id)
    
    @property
    def read_type(self) -> ReadTypeEnum:
        return ReadType.get(self.read_type_id)
    
