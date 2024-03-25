from datetime import datetime
from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

from ..categories import ExperimentStatus, ExperimentStatusEnum, FlowCellType, FlowCellTypeEnum
from .Links import ExperimentFileLink, ExperimentCommentLink

if TYPE_CHECKING:
    from .Pool import Pool
    from .Sequencer import Sequencer
    from .User import User
    from .File import File
    from .Comment import Comment
    from .SeqQuality import SeqQuality
    from .SeqRun import SeqRun
    from .Lane import Lane


class Experiment(Base):
    __tablename__ = "experiment"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(16), nullable=False, unique=True, index=True)
    
    timestamp: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    
    r1_cycles: Mapped[int] = mapped_column(nullable=False)
    r2_cycles: Mapped[Optional[int]] = mapped_column(nullable=True)
    i1_cycles: Mapped[int] = mapped_column(nullable=False)
    i2_cycles: Mapped[Optional[int]] = mapped_column(nullable=True)

    flowcell_type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    num_lanes: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    operator_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    operator: Mapped["User"] = relationship("User", lazy="joined")

    sequencer_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("sequencer.id"), nullable=False)
    sequencer: Mapped["Sequencer"] = relationship("Sequencer", lazy="select")

    # check_barcode_clashes_workflow_done: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    # qc_pools_workflow_done: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    # dilute_pools_workflow_done: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    
    seq_run: Mapped[Optional["SeqRun"]] = relationship("SeqRun", lazy="joined", primaryjoin="Experiment.name == SeqRun.experiment_name", foreign_keys=name)

    pools: Mapped[list["Pool"]] = relationship("Pool", lazy="select")
    lanes: Mapped[list["Lane"]] = relationship("Lane", lazy="select", cascade="delete")
    files: Mapped[list["File"]] = relationship("File", secondary=ExperimentFileLink.__tablename__, lazy="select", cascade="delete")
    comments: Mapped[list["Comment"]] = relationship("Comment", secondary=ExperimentCommentLink.__tablename__, lazy="select", cascade="delete")
    read_qualities: Mapped[list["SeqQuality"]] = relationship("SeqQuality", back_populates="experiment", lazy="select", cascade="delete")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "flowcell_id", "timestamp", "status_id", "sequencer_id", "num_lanes", "num_libraries", "flowcell_type_id"]

    @property
    def status(self) -> ExperimentStatusEnum:
        return ExperimentStatus.get(self.status_id)
    
    @property
    def flowcell_type(self) -> FlowCellTypeEnum:
        return FlowCellType.get(self.flowcell_type_id)
    
    def is_deleteable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def is_editable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def is_submittable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def timestamp_to_str(self) -> str:
        return self.timestamp.strftime('%Y-%m-%d %H:%M')
    
    def __str__(self) -> str:
        return f"Experiment(id={self.id}, num_lanes={self.num_lanes})"
    
    def search_name(self) -> str:
        return self.name
    
    def search_value(self) -> int:
        return self.id