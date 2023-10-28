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

    @abstractmethod
    def search_value(self) -> Union[int, str]:
        ...
    
    @abstractmethod
    def search_name(self) -> str:
        ...
    
    @abstractmethod
    def search_description(self) -> Optional[str]:
        ...