from typing import Optional, TYPE_CHECKING, ClassVar, List

from sqlmodel import Field, SQLModel, Relationship

from ..tools import SearchResult

if TYPE_CHECKING:
    from .Barcode import Barcode


class Adapter(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=32, index=True)
    index_kit_id: Optional[int] = Field(nullable=True, foreign_key="indexkit.id")

    barcode_1_id: Optional[int] = Field(nullable=True, foreign_key="barcode.id", default=None)
    barcode_1: Optional["Barcode"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "primaryjoin": "Adapter.barcode_1_id == Barcode.id"
        },
        
    )

    barcode_2_id: Optional[int] = Field(nullable=True, foreign_key="barcode.id", default=None)
    barcode_2: Optional["Barcode"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "primaryjoin": "Adapter.barcode_2_id == Barcode.id"
        },
    )

    barcode_3_id: Optional[int] = Field(nullable=True, foreign_key="barcode.id", default=None)
    barcode_3: Optional["Barcode"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "primaryjoin": "Adapter.barcode_3_id == Barcode.id"
        },
    )

    barcode_4_id: Optional[int] = Field(nullable=True, foreign_key="barcode.id", default=None)
    barcode_4: Optional["Barcode"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "primaryjoin": "Adapter.barcode_4_id == Barcode.id"
        },
    )

    sortable_fields: ClassVar[List[str]] = ["id", "name"]

    def name_class(self) -> str:
        return "latin"
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return None
    
    def __str__(self) -> str:
        return f"Adapter({self.name})"
        
