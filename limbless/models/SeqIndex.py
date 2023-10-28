from typing import Optional, TYPE_CHECKING, ClassVar, List

from sqlmodel import Field, SQLModel, Relationship

from ..tools import SearchResult

if TYPE_CHECKING:
    from .IndexKit import IndexKit
    from .SeqAdapter import SeqAdapter


class SeqIndex(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    sequence: str = Field(nullable=False, max_length=128, index=True)
    workflow: Optional[str] = Field(nullable=True, max_length=16)
    type: str = Field(nullable=False, max_length=16, index=True)

    adapter_id: int = Field(nullable=False, foreign_key="seqadapter.id")
    adapter: "SeqAdapter" = Relationship(
        back_populates="indices",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    index_kit_id: int = Field(nullable=False, foreign_key="indexkit.id")
    index_kit: "IndexKit" = Relationship(
        sa_relationship_kwargs={"lazy": "joined"},
    )

    sortable_fields: ClassVar[List[str]] = ["id", "sequence", "type", "adapter_id", "index_kit_id"]

    def __str__(self):
        return f"SeqIndex('{self.sequence}', {self.type})"

    def __repr__(self) -> str:
        return f"{self.sequence} [{self.type}]"
    
    def name_class(self) -> str:
        return "latin"
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.sequence
    
    def search_description(self) -> Optional[str]:
        return self.workflow
