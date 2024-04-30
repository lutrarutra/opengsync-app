from datetime import datetime
from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from .Base import Base
from ..categories import ExperimentStatus, ExperimentStatusEnum, FlowCellTypeEnum, ExperimentWorkFlow, ExperimentWorkFlowEnum
from .Links import ExperimentFileLink, ExperimentCommentLink, ExperimentPoolLink

if TYPE_CHECKING:
    from .Pool import Pool
    from .Sequencer import Sequencer
    from .User import User
    from .File import File
    from .Comment import Comment
    from .SeqQuality import SeqQuality
    from .SeqRun import SeqRun
    from .Lane import Lane
    from .actions import ExperimentAction


class Experiment(Base):
    __tablename__ = "experiment"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(16), nullable=False, unique=True, index=True)
    
    timestamp_created_utc: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=sa.func.now())
    timestamp_finished_utc: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(), nullable=True, default=None)
    
    r1_cycles: Mapped[int] = mapped_column(nullable=False)
    r2_cycles: Mapped[Optional[int]] = mapped_column(nullable=True)
    i1_cycles: Mapped[int] = mapped_column(nullable=False)
    i2_cycles: Mapped[Optional[int]] = mapped_column(nullable=True)
    num_lanes: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    workflow_id: Mapped[int] = mapped_column(sa.Integer)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    operator_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    operator: Mapped["User"] = relationship("User", lazy="joined")

    sequencer_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("sequencer.id"), nullable=False)
    sequencer: Mapped["Sequencer"] = relationship("Sequencer", lazy="select")

    seq_run: Mapped[Optional["SeqRun"]] = relationship("SeqRun", lazy="joined", primaryjoin="Experiment.name == SeqRun.experiment_name", foreign_keys=name)

    pools: Mapped[list["Pool"]] = relationship("Pool", secondary=ExperimentPoolLink.__tablename__, lazy="select")
    lanes: Mapped[list["Lane"]] = relationship("Lane", lazy="select", order_by="Lane.number", cascade="merge, save-update, delete, delete-orphan")
    files: Mapped[list["File"]] = relationship("File", secondary=ExperimentFileLink.__tablename__, lazy="select", cascade="delete")
    comments: Mapped[list["Comment"]] = relationship("Comment", secondary=ExperimentCommentLink.__tablename__, lazy="select", cascade="delete")
    read_qualities: Mapped[list["SeqQuality"]] = relationship("SeqQuality", back_populates="experiment", lazy="select", cascade="delete")
    actions: Mapped[list["ExperimentAction"]] = relationship("ExperimentAction", lazy="select", order_by="ExperimentAction.status_id.desc()", cascade="merge, save-update, delete, delete-orphan")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "flowcell_id", "timestamp_created_utc", "timestamp_finished_utc", "status_id", "sequencer_id", "num_lanes", "flowcell_type_id", "workflow_id"]

    @property
    def status(self) -> ExperimentStatusEnum:
        return ExperimentStatus.get(self.status_id)
    
    @property
    def flowcell_type(self) -> FlowCellTypeEnum:
        return self.workflow.flow_cell_type
    
    @property
    def workflow(self) -> ExperimentWorkFlowEnum:
        return ExperimentWorkFlow.get(self.workflow_id)
    
    @property
    def timestamp_created(self) -> datetime:
        return localize(self.timestamp_created_utc)
    
    @property
    def timestamp_finished(self) -> Optional[datetime]:
        if self.timestamp_finished_utc is None:
            return None
        return localize(self.timestamp_finished_utc)
    
    def is_deleteable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def is_editable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def is_submittable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def timestamp_created_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        return self.timestamp_created.strftime(fmt)
    
    def timestamp_finished_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        if (ts := self.timestamp_finished) is None:
            return ""
        return ts.strftime(fmt)
    
    def __str__(self) -> str:
        return f"Experiment(id={self.id}, num_lanes={self.num_lanes})"
    
    def search_name(self) -> str:
        return self.name
    
    def search_value(self) -> int:
        return self.id