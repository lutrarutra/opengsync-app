from typing import Optional, List, TYPE_CHECKING, ClassVar

from pydantic import PrivateAttr
from sqlmodel import Field, SQLModel, Relationship

from .Links import LibrarySampleLink, RunLibraryLink, LibrarySeqRequestLink
from ..categories import LibraryType
from ..tools.SearchResult import SearchResult

if TYPE_CHECKING:
    from .IndexKit import IndexKit
    from .Sample import Sample
    from .Run import Run
    from .User import User
    from .SeqRequest import SeqRequest


class LibraryTypeId(SQLModel, table=True):
    id: int = Field(nullable=False, primary_key=True)

    @property
    def library_type(self) -> LibraryType:
        return LibraryType.get(self.id)


class Library(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True)
    library_type_id: int = Field(nullable=False)

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
    runs: List["Run"] = Relationship(
        back_populates="libraries", link_model=RunLibraryLink,
        sa_relationship_kwargs={"lazy": "joined"}
    )

    seq_requests: List["SeqRequest"] = Relationship(
        back_populates="libraries",
        link_model=LibrarySeqRequestLink
    )

    sortable_fields: ClassVar[List[str]] = ["id", "name", "library_type_id", "owner_id"]

    _num_samples: int = PrivateAttr(0)
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

    @property
    def is_raw_library(self) -> bool:
        return self.index_kit_id is None

    def is_editable(self) -> bool:
        return len(self.samples) == 0
    
    def to_search_result(self) -> SearchResult:
        return SearchResult(
            value=self.id,
            name=self.name,
            description=self.library_type.value.name,
        )
