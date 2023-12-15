from typing import Optional, List, TYPE_CHECKING

from sqlmodel import Field, SQLModel, Relationship

from ..tools import SearchResult

if TYPE_CHECKING:
    from .Barcode import Barcode


class IndexKit(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True, unique=True)

    num_indices_per_adapter: int = Field(nullable=False)

    barcodes: List["Barcode"] = Relationship(
        back_populates="index_kit",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    def __str__(self):
        return self.name
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return None
