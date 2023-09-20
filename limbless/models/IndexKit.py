from typing import Optional, List, TYPE_CHECKING
from pydantic import PrivateAttr

from sqlmodel import Field, SQLModel, Relationship

from .Links import IndexKitLibraryType
from .Library import LibraryTypeId

if TYPE_CHECKING:
    from .SeqAdapter import SeqAdapter


class IndexKit(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True, unique=True)

    adapters: list["SeqAdapter"] = Relationship(
        back_populates="index_kit"
    )

    library_type_ids: List[LibraryTypeId] = Relationship(
        link_model=IndexKitLibraryType,
        sa_relationship_kwargs={"lazy": "joined"},
    )

    _num_adapters: int = PrivateAttr()

    def __str__(self):
        return self.name
    
    @property
    def library_types(self):
        return [library_type.library_type for library_type in self.library_type_ids]
