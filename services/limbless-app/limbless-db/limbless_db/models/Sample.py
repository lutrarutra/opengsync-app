from typing import Optional, List, TYPE_CHECKING, ClassVar

from sqlmodel import Field, SQLModel, Relationship

from ..core.SearchResult import SearchResult


if TYPE_CHECKING:
    from .Project import Project
    from .Links import SampleLibraryLink
    from .User import User


class Sample(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True)
    num_libraries: int = Field(nullable=False, default=0)

    project_id: int = Field(nullable=False, foreign_key="project.id")
    project: "Project" = Relationship(
        back_populates="samples",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    owner_id: int = Field(nullable=False, foreign_key="lims_user.id")
    owner: "User" = Relationship(
        back_populates="samples",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    library_links: list["SampleLibraryLink"] = Relationship(
        back_populates="sample",
        sa_relationship_kwargs={"lazy": "select"}
    )

    sortable_fields: ClassVar[List[str]] = ["id", "name", "project_id", "owner_id", "num_libraries"]

    def to_dict(self):
        data = {
            "id": self.id,
            "name": self.name,
            "project": self.project.name,
        }
        return data

    def __str__(self):
        return f"Sample(id: {self.id}, name:{self.name})"

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return self.project.name
    
    def is_editable(self) -> bool:
        return self.num_libraries == 0
