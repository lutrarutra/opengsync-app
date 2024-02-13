
from typing import Optional, List, TYPE_CHECKING, ClassVar

from sqlmodel import Field, SQLModel, Relationship

from ..core.SearchResult import SearchResult
from ..core.categories import FeatureType

if TYPE_CHECKING:
    from .Feature import Feature


class FeatureKit(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True, unique=True)

    features: List["Feature"] = Relationship(
        back_populates="feature_kit",
        sa_relationship_kwargs={"lazy": "select"},
    )

    type_id: int = Field(nullable=False)

    sortable_fields: ClassVar[list[str]] = ["id", "name"]

    @property
    def type(self) -> FeatureType:
        return FeatureType.get(self.type_id)

    def __str__(self):
        return self.name
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return None
