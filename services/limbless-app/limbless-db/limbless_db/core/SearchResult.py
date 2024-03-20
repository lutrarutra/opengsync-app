from typing import Union, Optional

from abc import ABC, abstractmethod


class SearchResult(ABC):
    __config__ = None

    def show_value(self) -> bool:
        return False
    
    def name_class(self) -> str:
        return ""
    
    def description_class(self) -> str:
        return ""
    
    def to_str(self) -> str:
        res = self.search_name()
        if self.show_value():
            res += f" [{self.search_value()}]"
        if self.search_description():
            res += f" ({self.search_description()})"

        return res

    @abstractmethod
    def search_value(self) -> Union[int, str]:
        ...
    
    @abstractmethod
    def search_name(self) -> str:
        ...
    
    def search_description(self) -> Optional[str]:
        return None


class StaticSearchResult(SearchResult):
    def __init__(self, value: Union[int, str], name: str, description: Optional[str] = None):
        super().__init__()
        self.value = value
        self.name = name
        self.description = description

    def search_value(self) -> Union[int, str]:
        return self.value
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return self.description