from typing import Optional, TYPE_CHECKING, ClassVar, List

from sqlmodel import Field, SQLModel, Relationship

from ..core.SearchResult import SearchResult
from ..categories import BarcodeType, BarcodeTypeEnum

if TYPE_CHECKING:
    from .IndexKit import IndexKit


class Barcode(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    sequence: str = Field(nullable=False, max_length=64, index=True)
    adapter: Optional[str] = Field(nullable=True, max_length=32, index=True)
    
    index_kit_id: Optional[int] = Field(nullable=True, foreign_key="indexkit.id")
    index_kit: Optional["IndexKit"] = Relationship(
        back_populates="barcodes",
        sa_relationship_kwargs={"lazy": "joined"},
    )

    type_id: int = Field(nullable=False)

    sortable_fields: ClassVar[List[str]] = ["id", "sequence", "type", "adapter_id", "index_kit_id"]

    def __str__(self):
        return f"Barcode('{self.sequence}', {self.type})"
    
    @property
    def type(self) -> BarcodeTypeEnum:
        return BarcodeType.get(self.type_id)
    
    @staticmethod
    def reverse_complement(sequence: str) -> str:
        return "".join([{"A": "T", "T": "A", "G": "C", "C": "G"}[base] for base in sequence[::-1]])
    
    def name_class(self) -> str:
        return "latin"
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.sequence
    
    def search_description(self) -> Optional[str]:
        return self.type.name
