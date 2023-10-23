from typing import Union, Optional

from dataclasses import dataclass


@dataclass
class SearchResult():
    value: Union[int, str]
    name: str
    description: Optional[str] = None
    show_value: bool = False

    name_class: str = ""
    description_class: str = ""
