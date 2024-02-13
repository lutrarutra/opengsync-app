from typing import Optional

from sqlmodel import Field, SQLModel

from ..core.SearchResult import SearchResult


class Organism(SQLModel, SearchResult, table=True):
    tax_id: int = Field(default=None, primary_key=True)
    scientific_name: str = Field(nullable=False, max_length=128, index=True)
    common_name: Optional[str] = Field(nullable=True, max_length=128, index=True)
    category: int = Field(nullable=False)

    def __str__(self) -> str:
        _val = f"{self.scientific_name} [{self.tax_id}]"
        if self.common_name:
            _val += f" ({self.common_name})"
        return _val

    @property
    def id(self):
        return self.tax_id
    
    def show_value(self) -> bool:
        return True
    
    def name_class(self) -> str:
        return "latin"
    
    def search_value(self) -> int:
        return self.tax_id
    
    def search_name(self) -> str:
        return self.scientific_name
    
    def search_description(self) -> Optional[str]:
        return self.common_name
