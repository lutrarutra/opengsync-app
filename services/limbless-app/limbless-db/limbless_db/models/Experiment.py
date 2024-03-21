from datetime import datetime
from typing import Optional, List, TYPE_CHECKING, ClassVar
from pydantic import PrivateAttr

import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship

from ..categories import ExperimentStatus, ExperimentStatusEnum, FlowCellType, FlowCellTypeEnum
from ..core.SearchResult import SearchResult
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


class Experiment(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=16, unique=True, index=True)
    
    flowcell_type_id: int = Field(nullable=False)

    r1_cycles: int = Field(nullable=False)
    r2_cycles: Optional[int] = Field(nullable=True)
    i1_cycles: int = Field(nullable=False)
    i2_cycles: Optional[int] = Field(nullable=True)

    operator_id: int = Field(nullable=False, foreign_key="lims_user.id")
    operator: "User" = Relationship(sa_relationship_kwargs={"lazy": "select"})
    
    num_lanes: int = Field(nullable=False)

    timestamp: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))

    status_id: int = Field(nullable=False, default=0)

    sequencer_id: int = Field(nullable=False, foreign_key="sequencer.id")
    sequencer: "Sequencer" = Relationship(sa_relationship_kwargs={"lazy": "joined"})

    pools: List["Pool"] = Relationship(
        sa_relationship_kwargs={"lazy": "select"},
    )

    lanes: list["Lane"] = Relationship(
        sa_relationship_kwargs={"lazy": "select", "cascade": "delete"}
    )

    sortable_fields: ClassVar[List[str]] = ["id", "name", "flowcell_id", "timestamp", "status_id", "sequencer_id", "num_lanes", "num_libraries", "flowcell_type_id"]

    files: list["File"] = Relationship(
        link_model=ExperimentFileLink, sa_relationship_kwargs={"lazy": "select", "cascade": "delete"},
    )
    comments: list["Comment"] = Relationship(
        link_model=ExperimentCommentLink,
        sa_relationship_kwargs={"lazy": "select", "cascade": "delete"}
    )

    read_qualities: list["SeqQuality"] = Relationship(
        back_populates="experiment",
        sa_relationship_kwargs={"lazy": "select", "cascade": "delete"}
    )

    _seq_run_: Optional["SeqRun"] = PrivateAttr()

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
    
    @property
    def seq_run(self) -> Optional["SeqRun"]:
        return self._seq_run_
    
    def __str__(self) -> str:
        return f"Experiment(id={self.id}, num_lanes={self.num_lanes})"
    
    def search_name(self) -> str:
        return self.name
    
    def search_value(self) -> int:
        return self.id