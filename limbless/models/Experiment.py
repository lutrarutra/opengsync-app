from typing import Optional, List, TYPE_CHECKING, ClassVar

from sqlmodel import Field, SQLModel, TIMESTAMP, text, Column, Relationship
from datetime import datetime

from ..categories import ExperimentStatus
from .Links import ExperimentLibraryLink

if TYPE_CHECKING:
    from .Library import Library
    from .Sequencer import Sequencer


class Experiment(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    
    flowcell: str = Field(nullable=False, max_length=64)
    r1_cycles: int = Field(nullable=False)
    r2_cycles: Optional[int] = Field(nullable=True)
    i1_cycles: int = Field(nullable=False)
    i2_cycles: Optional[int] = Field(nullable=True)
    
    num_lanes: int = Field(nullable=False, default=1)
    num_libraries: int = Field(nullable=False, default=0)

    timestamp: datetime = Field(sa_column=Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    ))

    status: int = Field(nullable=False, default=0)

    sequencer_id: int = Field(nullable=False, foreign_key="sequencer.id")
    sequencer: "Sequencer" = Relationship(sa_relationship_kwargs={"lazy": "joined"})

    libraries: List["Library"] = Relationship(
        back_populates="experiments", link_model=ExperimentLibraryLink
    )

    sortable_fields: ClassVar[List[str]] = ["id", "flowcell", "timestamp", "status", "sequencer_id"]

    @property
    def status_type(self) -> ExperimentStatus:
        return ExperimentStatus.get(self.status)
    
    def is_deleteable(self) -> bool:
        return self.status_type == ExperimentStatus.DRAFT
    
    def is_editable(self) -> bool:
        return self.status_type == ExperimentStatus.DRAFT
