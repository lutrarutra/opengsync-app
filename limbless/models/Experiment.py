from datetime import datetime
from typing import Optional, List, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship

from ..categories import ExperimentStatus
from .Links import ExperimentPoolLink, SeqRequestExperimentLink

if TYPE_CHECKING:
    from .Pool import Pool
    from .Sequencer import Sequencer
    from .User import User
    from .SeqRequest import SeqRequest


class Experiment(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    
    flowcell: str = Field(nullable=False, max_length=64)
    r1_cycles: int = Field(nullable=False)
    r2_cycles: Optional[int] = Field(nullable=True)
    i1_cycles: int = Field(nullable=False)
    i2_cycles: Optional[int] = Field(nullable=True)

    sequencing_person_id: int = Field(nullable=False, foreign_key="lims_user.id")
    sequencing_person: "User" = Relationship(sa_relationship_kwargs={"lazy": "joined"})
    
    num_lanes: int = Field(nullable=False, default=1)
    num_pools: int = Field(nullable=False, default=0)

    timestamp: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))

    status_id: int = Field(nullable=False, default=0)

    sequencer_id: int = Field(nullable=False, foreign_key="sequencer.id")
    sequencer: "Sequencer" = Relationship(sa_relationship_kwargs={"lazy": "joined"})

    pools: List["Pool"] = Relationship(
        back_populates="experiments", link_model=ExperimentPoolLink,
        sa_relationship_kwargs={"lazy": "select"},
    )
    seq_requests: List["SeqRequest"] = Relationship(
        back_populates="experiments", link_model=SeqRequestExperimentLink,
        sa_relationship_kwargs={"lazy": "select"},
    )

    sortable_fields: ClassVar[List[str]] = ["id", "flowcell", "timestamp", "status", "sequencer_id", "num_lanes", "num_libraries"]

    @property
    def status(self) -> ExperimentStatus:
        return ExperimentStatus.get(self.status_id)
    
    def is_deleteable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def is_editable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def is_submittable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT and self.is_all_pools_indexed()
    
    def is_all_pools_indexed(self) -> bool:
        if len(self.pools) == 0:
            return False
        for pool in self.pools:
            if not pool.is_indexed():
                return False
        return True
    
    def timestamp_to_str(self) -> str:
        return self.timestamp.strftime('%Y-%m-%d %H:%M')
