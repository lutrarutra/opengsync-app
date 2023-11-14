from typing import Optional, TYPE_CHECKING, ClassVar, List

from sqlmodel import Field, SQLModel, Relationship

from ..tools import SearchResult
from ..categories import BarcodeType

if TYPE_CHECKING:
    from .Adapter import Adapter


class Barcode(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    sequence: str = Field(nullable=False, max_length=128, index=True)

    adapter_id: int = Field(nullable=False, foreign_key="adapter.id")
    adapter: "Adapter" = Relationship(
        back_populates="barcodes",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    type_id: int = Field(nullable=False)

    sortable_fields: ClassVar[List[str]] = ["id", "sequence", "type", "adapter_id", "index_kit_id"]

    def __str__(self):
        return f"Barcode('{self.sequence}', {self.type})"

    def __repr__(self) -> str:
        return f"{self.sequence} [{self.type}]"
    
    @property
    def type(self) -> BarcodeType:
        return BarcodeType.get(self.type_id)
    
    def name_class(self) -> str:
        return "latin"
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.sequence
    
    def search_description(self) -> Optional[str]:
        return self.type.value.name
