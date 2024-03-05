from datetime import datetime
from typing import Optional, List, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship

from ..core.categories import ExperimentStatus, FlowCellType, AssayType
from .Links import ExperimentPoolLink, SeqRequestExperimentLink, ExperimentFileLink, ExperimentCommentLink

if TYPE_CHECKING:
    from .Pool import Pool
    from .Sequencer import Sequencer
    from .User import User
    from .SeqRequest import SeqRequest
    from .File import File
    from .Comment import Comment
    from .SeqQuality import SeqQuality


class Experiment(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    
    flowcell_id: Optional[str] = Field(nullable=True, max_length=64)
    flowcell_type_id: int = Field(nullable=False)

    assay_type_id: int = Field(nullable=False)

    r1_cycles: int = Field(nullable=False)
    r2_cycles: Optional[int] = Field(nullable=True)
    i1_cycles: int = Field(nullable=False)
    i2_cycles: Optional[int] = Field(nullable=True)

    sequencing_person_id: int = Field(nullable=False, foreign_key="lims_user.id")
    sequencing_person: "User" = Relationship(sa_relationship_kwargs={"lazy": "joined"})
    
    num_lanes: int = Field(nullable=False, default=0)
    num_pools: int = Field(nullable=False, default=0)

    timestamp: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))

    status_id: int = Field(nullable=False, default=0)

    sequencer_id: int = Field(nullable=False, foreign_key="sequencer.id")
    sequencer: "Sequencer" = Relationship(sa_relationship_kwargs={"lazy": "joined"})

    pools: List["Pool"] = Relationship(
        back_populates="experiments", link_model=ExperimentPoolLink,
        sa_relationship_kwargs={"lazy": "select", "overlaps": "experiment_links,pool,experiment"},
    )
    pool_links: List["ExperimentPoolLink"] = Relationship(
        back_populates="experiment",
        sa_relationship_kwargs={"lazy": "select", "overlaps": "experiments,pools,experiment"},
    )

    seq_requests: List["SeqRequest"] = Relationship(
        back_populates="experiments", link_model=SeqRequestExperimentLink,
        sa_relationship_kwargs={"lazy": "select"},
    )

    sortable_fields: ClassVar[List[str]] = ["id", "flowcell", "timestamp", "status", "sequencer_id", "num_lanes", "num_libraries"]

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

    @property
    def status(self) -> ExperimentStatus:
        return ExperimentStatus.get(self.status_id)
    
    @property
    def assay_type(self) -> AssayType:
        return AssayType.get(self.assay_type_id)
    
    @property
    def flowcell_type(self) -> FlowCellType:
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
        return f"Experiment(id={self.id}, num_lanes={self.num_lanes}, num_pools={self.num_pools})"
