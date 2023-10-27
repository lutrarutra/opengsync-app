from typing import Union, Optional

from abc import ABC, abstractmethod


class SearchResult(ABC):
    __config__ = None
    
    def __init__(self, show_value: bool = False, name_class: str = "", description_class: str = ""):
        self.show_value = show_value
        self.name_class = name_class
        self.description_class = description_class

    @abstractmethod
    def search_value(self) -> Union[int, str]:
        ...
    
    @abstractmethod
    def search_name(self) -> str:
        ...
    
    @abstractmethod
    def search_description(self) -> Optional[str]:
        ...