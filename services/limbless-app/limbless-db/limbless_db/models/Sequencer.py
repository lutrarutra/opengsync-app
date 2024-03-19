from typing import Optional

from sqlmodel import Field, SQLModel

from ..core.SearchResult import SearchResult
from ..categories import SequencerType, SequencerTypeEnum


class Sequencer(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)

    name: str = Field(nullable=False, max_length=32, unique=True, index=True)
    type_id: int = Field(nullable=False)
    ip: Optional[str] = Field(nullable=True, max_length=64, unique=False)

    @property
    def type(self) -> SequencerTypeEnum:
        return SequencerType.get(self.type_id)

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return self.ip