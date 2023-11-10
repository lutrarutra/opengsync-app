from typing import Optional, List, TYPE_CHECKING

from sqlmodel import Field, SQLModel, Relationship

from .Links import IndexKitLibraryType
from .Library import LibraryTypeId
from ..tools import SearchResult

if TYPE_CHECKING:
    from .Adapter import Adapter


class IndexKit(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True, unique=True)

    num_adapters: int = Field(nullable=False, default=0)

    adapters: list["Adapter"] = Relationship(
        back_populates="index_kit"
    )

    library_type_ids: List[LibraryTypeId] = Relationship(
        link_model=IndexKitLibraryType,
        sa_relationship_kwargs={"lazy": "joined"},
    )

    def __str__(self):
        return self.name
    
    @property
    def library_types(self):
        return [library_type.library_type for library_type in self.library_type_ids]
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return None
