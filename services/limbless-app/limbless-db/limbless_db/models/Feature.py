
from typing import TYPE_CHECKING, ClassVar, Optional

from sqlmodel import Field, SQLModel, Relationship

from ..core.SearchResult import SearchResult
from ..categories import FeatureType

if TYPE_CHECKING:
    from .FeatureKit import FeatureKit


class Feature(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=32, index=True)
    sequence: str = Field(nullable=False, max_length=32, index=True)
    pattern: str = Field(nullable=False, max_length=32)
    read: str = Field(nullable=False, max_length=8)
    target_name: Optional[str] = Field(nullable=True, max_length=32, index=True)
    target_id: Optional[str] = Field(nullable=True, max_length=32, index=True)

    type_id: int = Field(nullable=False)

    feature_kit_id: Optional[int] = Field(nullable=True, foreign_key="featurekit.id")
    feature_kit: Optional["FeatureKit"] = Relationship(
        back_populates="features",
        sa_relationship_kwargs={"lazy": "select"},
    )

    sortable_fields: ClassVar[list[str]] = ["id", "name", "target_name", "target_id", "feature_kit_id"]

    def __str__(self) -> str:
        return f"Feature('{self.sequence}', {self.pattern}, {self.read}{f', {self.feature_kit.name}' if self.feature_kit else ''})"
    
    @property
    def type(self) -> FeatureType:
        return FeatureType.get(self.type_id)
    
    def search_name(self) -> str:
        return self.name
    
    def search_value(self) -> int:
        return self.id
    
    def search_description(self) -> Optional[str]:
        return self.type.name