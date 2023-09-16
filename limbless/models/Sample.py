from typing import Optional, List, TYPE_CHECKING

from sqlmodel import Field, SQLModel, Relationship

from .Links import LibrarySampleLink
from ..tools import SearchResult

if TYPE_CHECKING:
    from .Organism import Organism
    from .Project import Project
    from .Library import Library
    from .SeqIndex import SeqIndex


class Sample(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True)

    organism_id: int = Field(nullable=False, foreign_key="organism.tax_id")
    organism: "Organism" = Relationship(sa_relationship_kwargs={"lazy": "joined"})

    project_id: int = Field(nullable=False, foreign_key="project.id")
    project: "Project" = Relationship(back_populates="samples")

    libraries: List["Library"] = Relationship(
        back_populates="samples",
        link_model=LibrarySampleLink
    )
    indices: List["SeqIndex"] = Relationship(
        link_model=LibrarySampleLink,
        sa_relationship_kwargs={"lazy": "noload", "viewonly": True}
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "organism": self.organism,
        }

    def __str__(self):
        return f"Sample(id: {self.id}, name:{self.name}, organism:{self.organism})"

    def to_search_result(self) -> SearchResult:
        return SearchResult(self.id, self.name, self.project.name)
