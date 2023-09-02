from typing import Optional, List

from pydantic import PrivateAttr
from sqlmodel import Field, SQLModel, Relationship

from .Links import LibrarySampleLink, RunLibraryLink
from ..core.categories import LibraryType

class Library(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True, unique=True)
    library_type_id: int = Field(nullable=False)

    samples: List["Sample"] = Relationship(
        back_populates="libraries", link_model=LibrarySampleLink
    )
    runs: List["Run"] = Relationship(
        back_populates="libraries", link_model=RunLibraryLink
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