from typing import Optional, List, TYPE_CHECKING, ClassVar

from sqlmodel import Field, SQLModel, Relationship

from ..categories import LibraryType
from ..tools import SearchResult
from .Links import ExperimentLibraryLink

if TYPE_CHECKING:
    from .IndexKit import IndexKit
    from .Sample import Sample
    from .Experiment import Experiment


class LibraryTypeId(SQLModel, table=True):
    id: int = Field(nullable=False, primary_key=True)

    @property
    def library_type(self) -> LibraryType:
        return LibraryType.get(self.id)


class Library(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    workflow: Optional[str] = Field(nullable=True, max_length=16)
    library_type_id: int = Field(nullable=False)

    sample_id: int = Field(nullable=False, foreign_key="sample.id")
    sample: "Sample" = Relationship(
        sa_relationship_kwargs={"lazy": "joined"}
    )

    experiments: list["Experiment"] = Relationship(
        back_populates="libraries",
        sa_relationship_kwargs={"lazy": "select"},
        link_model=ExperimentLibraryLink
    )

    sortable_fields: ClassVar[List[str]] = ["id", "name", "library_type_id"]

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.sample.name,
            "library_type": self.library_type.value.name,
        }

    @property
    def library_type(self) -> LibraryType:
        return LibraryType.get(self.library_type_id)
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.sample.name
    
    def search_description(self) -> Optional[str]:
        return self.library_type.value.name
