from typing import Optional, List
from enum import Enum
from pydantic import PrivateAttr

from sqlmodel import Field, SQLModel, TIMESTAMP, text, Column, Relationship
from datetime import datetime

from .Links import RunLibraryLink
from .Experiment import Experiment

class Run(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    lane: int = Field(nullable=False)
    r1_cycles: int = Field(nullable=False)
    r2_cycles: Optional[int] = Field(nullable=True)
    i1_cycles: int = Field(nullable=False)
    i2_cycles: Optional[int] = Field(nullable=True)
    experiment_id: int = Field(nullable=False, foreign_key="experiment.id")
    
    experiment: "Experiment" = Relationship(back_populates="runs")
    libraries: List["Library"] = Relationship(
        back_populates="runs", link_model=RunLibraryLink
    )

    _num_samples: int = PrivateAttr(default=0)
