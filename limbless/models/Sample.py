from typing import Optional, List
from enum import Enum

from sqlmodel import Field, SQLModel, Relationship

from .Links import LibrarySampleLink

class Sample(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True) # TODO: Unique + tests
    organism: str = Field(nullable=False, max_length=64)
    index1: str = Field(nullable=False, max_length=128)
    index2: Optional[str] = Field(nullable=True, max_length=128)
    project_id: int = Field(nullable=False, foreign_key="project.id")

    project: "Project" = Relationship(back_populates="samples")

    libraries: List["Library"] = Relationship(
        back_populates="samples", link_model=LibrarySampleLink
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "organism": self.organism,
            "index1": self.index1,
            "index2": self.index2
        }

    def __str__(self):
        return f"Sample(id: {self.id}, name:{self.name})"