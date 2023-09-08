from typing import Optional, List, TYPE_CHECKING

from pydantic import PrivateAttr
from sqlmodel import Field, SQLModel, Relationship

from .Links import LibrarySampleLink, RunLibraryLink, LibraryUserLink
from ..categories import LibraryType

if TYPE_CHECKING:
    from .IndexKit import IndexKit
    from .Sample import Sample
    from .Run import Run
    from .User import User


class Library(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True, unique=True)
    library_type_id: int = Field(nullable=False)

    index_kit_id: int = Field(nullable=False, foreign_key="indexkit.id")
    index_kit: "IndexKit" = Relationship(
        sa_relationship_kwargs={"lazy": "joined"}
    )

    samples: List["Sample"] = Relationship(
        back_populates="libraries", link_model=LibrarySampleLink,
    )
    runs: List["Run"] = Relationship(
        back_populates="libraries", link_model=RunLibraryLink
    )
    users: List["User"] = Relationship(
        back_populates="libraries", link_model=LibraryUserLink
    )

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
        return LibraryType.as_dict()[self.library_type_id]
