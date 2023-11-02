from typing import Optional, List, TYPE_CHECKING, ClassVar

from pydantic import PrivateAttr
from sqlmodel import Field, SQLModel, Relationship

from .Links import LibrarySampleLink, ExperimentLibraryLink, LibrarySeqRequestLink
from ..categories import LibraryType
from ..tools import SearchResult

if TYPE_CHECKING:
    from .IndexKit import IndexKit
    from .Sample import Sample
    from .User import User
    from .SeqRequest import SeqRequest
    from .Experiment import Experiment


class LibraryTypeId(SQLModel, table=True):
    id: int = Field(nullable=False, primary_key=True)

    @property
    def library_type(self) -> LibraryType:
        return LibraryType.get(self.id)


class Library(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True)
    library_type_id: int = Field(nullable=False)
    
    num_samples: int = Field(nullable=False, default=0)
    num_experiments: int = Field(nullable=False, default=0)
    num_seq_requests: int = Field(nullable=False, default=0)

    index_kit_id: Optional[int] = Field(nullable=True, foreign_key="indexkit.id")
    index_kit: Optional["IndexKit"] = Relationship(
        sa_relationship_kwargs={"lazy": "joined"}
    )

    owner_id: int = Field(nullable=False, foreign_key="user.id")
    owner: "User" = Relationship(
        back_populates="libraries",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    samples: List["Sample"] = Relationship(
        back_populates="libraries", link_model=LibrarySampleLink,
    )
    experiments: List["Experiment"] = Relationship(
        back_populates="libraries", link_model=ExperimentLibraryLink,
    )

    seq_requests: List["SeqRequest"] = Relationship(
        back_populates="libraries",
        link_model=LibrarySeqRequestLink
    )

    sortable_fields: ClassVar[List[str]] = ["id", "name", "library_type_id", "owner_id", "num_samples", "num_experiments", "num_seq_requests"]

    _sample_path: str = PrivateAttr("")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "library_type": self.library_type,
        }

    @property
    def library_type(self) -> LibraryType:
        return LibraryType.get(self.library_type_id)

    def is_raw_library(self) -> bool:
        return self.index_kit_id is None

    def is_editable(self) -> bool:
        return self.num_samples == 0
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return self.library_type.value.name
