from typing import Optional, List

from pydantic import PrivateAttr
from sqlmodel import Field, SQLModel, Relationship

from .Links import LibrarySampleLink, RunLibraryLink

class Library(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True, unique=True)
    library_type: str = Field(nullable=False, max_length=64)

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