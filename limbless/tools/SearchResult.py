from typing import Union, Optional

from dataclasses import dataclass


@dataclass
class SearchResult():
    value: Union[int, str]
    name: str
    description: Optional[str] = None
