from typing import Optional, List, TYPE_CHECKING, ClassVar

from sqlmodel import Field, SQLModel, TIMESTAMP, text, Column, Relationship
from datetime import datetime

from ..categories import ExperimentStatus

if TYPE_CHECKING:
    from .Run import Run
    from .Sequencer import Sequencer


class Experiment(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    
    flowcell: str = Field(nullable=False, max_length=64)

    timestamp: datetime = Field(sa_column=Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    ))

    status: int = Field(nullable=False, default=0)

    sequencer_id: int = Field(nullable=False, foreign_key="sequencer.id")
    sequencer: "Sequencer" = Relationship(sa_relationship_kwargs={"lazy": "joined"})

    runs: List["Run"] = Relationship(back_populates="experiment")

    sortable_fields: ClassVar[List[str]] = ["id", "flowcell", "timestamp", "status", "sequencer_id"]

    @property
    def status_type(self) -> ExperimentStatus:
        return ExperimentStatus.get(self.status)
    
    def is_deleteable(self) -> bool:
        return self.status_type == ExperimentStatus.DRAFT
