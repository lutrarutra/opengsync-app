from typing import Optional, TYPE_CHECKING, Union

from sqlmodel import Field, SQLModel

from ..tools import SearchResult

if TYPE_CHECKING:
    pass


class Sequencer(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)

    name: str = Field(nullable=False, max_length=64, unique=True, index=True)
    ip: Optional[str] = Field(nullable=True, max_length=128, unique=False)

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return self.ip