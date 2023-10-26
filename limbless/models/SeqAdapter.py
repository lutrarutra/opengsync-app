from typing import Optional, TYPE_CHECKING, ClassVar, List

from sqlmodel import Field, SQLModel, Relationship

from ..tools.SearchResult import SearchResult

if TYPE_CHECKING:
    from .IndexKit import IndexKit
    from .SeqIndex import SeqIndex


class SeqAdapter(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=128, index=True)

    index_kit_id: int = Field(nullable=False, foreign_key="indexkit.id")
    index_kit: "IndexKit" = Relationship(
        back_populates="adapters",
        sa_relationship_kwargs={"lazy": "joined"},
    )

    indices: list["SeqIndex"] = Relationship(
        back_populates="adapter",
        sa_relationship_kwargs={"lazy": "joined"},
    )

    sortable_fields: ClassVar[List[str]] = ["id", "name", "index_kit_id"]

    def to_search_result(self) -> SearchResult:
        return SearchResult(
            self.id, self.name,
            description=", ".join([f"{index.sequence} [{index.type}{f' ({index.workflow})' if index.workflow is not None else ''}]" for index in self.indices])
        )