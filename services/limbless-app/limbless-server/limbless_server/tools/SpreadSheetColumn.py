from typing import Optional, Literal, Any, Type

from dataclasses import dataclass


@dataclass
class SpreadSheetColumn:
    column: str
    label: str
    name: str
    type: Literal["text", "numeric", "dropdown"]
    width: float
    var_type: Type
    source: Optional[Any] = None