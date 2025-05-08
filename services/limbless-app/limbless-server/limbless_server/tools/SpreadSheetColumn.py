from typing import Optional, Literal, Any, Type, Callable

from dataclasses import dataclass

from .. import logger


@dataclass
class SpreadSheetColumn:
    label: str
    name: str
    type: Literal["text", "numeric", "dropdown"]
    width: float
    var_type: Type
    source: Optional[Any] = None
    clean_up_fnc: Optional[Callable] = None
    letter: Optional[str] = None
    required: bool = False

    def clean_up(self, value: Any) -> Any:
        if self.clean_up_fnc is not None and value is not None:
            return self.clean_up_fnc(value)
        if isinstance(value, str):
            value = value.strip()
        return value
    
    def validate(self, value: Any) -> bool:
        if self.required and value is None:
            return False
        return True


class TextColumn(SpreadSheetColumn):
    def __init__(self, label: str, name: str, width: float, required: bool = False, clean_up_fnc: Optional[Callable] = None, letter: Optional[str] = None):
        super().__init__(label=label, name=name, type="text", width=width, var_type=str, clean_up_fnc=clean_up_fnc, letter=letter, required=required)


class IntegerColumn(SpreadSheetColumn):
    def __init__(self, label: str, name: str, width: float, required: bool = False, letter: Optional[str] = None):
        super().__init__(label=label, name=name, type="numeric", width=width, var_type=int, letter=letter, required=required)

    def validate(self, value: Any) -> bool:
        if not super().validate(value):
            return False
        
        if isinstance(value, str):
            try:
                value = int(value.strip())
            except ValueError:
                return False

        return True


class FloatColumn(SpreadSheetColumn):
    def __init__(self, label: str, name: str, width: float, required: bool = False, letter: Optional[str] = None):
        super().__init__(label=label, name=name, type="numeric", width=width, var_type=float, letter=letter, required=required)

    def validate(self, value: Any) -> bool:
        if not super().validate(value):
            return False
        
        if isinstance(value, str):
            try:
                value = float(value.strip())
            except ValueError:
                return False

        return True
    

class DropdownColumn(SpreadSheetColumn):
    def __init__(self, label: str, name: str, width: float, choices: list[Any], required: bool = False, letter: Optional[str] = None):
        super().__init__(label=label, name=name, type="dropdown", width=width, var_type=str, source=choices, letter=letter, required=required)

    def validate(self, value: Any) -> bool:
        if not super().validate(value):
            return False
        
        if isinstance(value, str):
            value = value.strip()

        if value not in self.source:
            return False

        return True