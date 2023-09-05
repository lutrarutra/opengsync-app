from typing import Optional, List, TYPE_CHECKING

from sqlmodel import Field, SQLModel, TIMESTAMP, text, Column, Relationship
from datetime import datetime

if TYPE_CHECKING:
    from .Run import Run


class Experiment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, unique=True, index=True)
    flowcell: str = Field(nullable=False, max_length=64)
    timestamp: datetime = Field(sa_column=Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    ))

    runs: List["Run"] = Relationship(back_populates="experiment")
