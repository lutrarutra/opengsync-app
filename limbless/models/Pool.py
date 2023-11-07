from typing import Optional, List, TYPE_CHECKING, ClassVar

from pydantic import PrivateAttr
from sqlmodel import Field, SQLModel, Relationship

from .Links import SamplePoolLink
from ..tools import SearchResult

if TYPE_CHECKING:
    from .Sample import Sample
    from .User import User


class Pool(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True)
    
    num_samples: int = Field(nullable=False, default=0)

    owner_id: int = Field(nullable=False, foreign_key="user.id")
    owner: "User" = Relationship(
        back_populates="pools",
        sa_relationship_kwargs={"lazy": "joined"}
    )
    samples: List["Sample"] = Relationship(
        back_populates="pools", link_model=SamplePoolLink,
    )

    sortable_fields: ClassVar[List[str]] = ["id", "name", "owner_id", "num_samples"]

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
        }
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return ""
