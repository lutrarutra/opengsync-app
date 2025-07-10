import pandas as pd

from typing import Optional, Literal, Any, Type, Callable

from dataclasses import dataclass

from .. import logger


@dataclass
class SpreadSheetException(Exception):
    message: str
    color: str = "#AED6F1"
    title: str = "Error"


class InvalidCellValue(SpreadSheetException):
    def __init__(self, message: str):
        super().__init__(message, "#F5B7B1", "Invalid Value")


class MissingCellValue(SpreadSheetException):
    def __init__(self, message: str):
        super().__init__(message, "#FAD7A0", "Missing Value")


class DuplicateCellValue(SpreadSheetException):
    def __init__(self, message: str):
        super().__init__(message, "#D7BDE2", "Duplicate Value")


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
        if pd.isna(value):
            if self.required:
                logger.error(f"Value for '{self.label}' is required but missing.")
                raise ValueError(f"Value for '{self.label}' is required but missing.")
            return None
        
        if isinstance(value, str):
            if not (value := value.strip()) and self.required:
                raise MissingCellValue(f"Value for '{self.label}' is required but missing.")
            
            if not value:
                value = None
                
        if self.clean_up_fnc is not None:
            return self.clean_up_fnc(value)
            
        return value
    
    def validate(self, value: Any):
        if self.required and value is None:
            raise MissingCellValue(f"Missing value for '{self.label}'")


class TextColumn(SpreadSheetColumn):
    def __init__(self, label: str, name: str, width: float, max_length: int, min_length: int = 0, required: bool = False, clean_up_fnc: Optional[Callable] = None, letter: Optional[str] = None):
        super().__init__(label=label, name=name, type="text", width=width, var_type=str, clean_up_fnc=clean_up_fnc, letter=letter, required=required)
        self.max_length = max_length
        self.min_length = min_length

    def validate(self, value: Any):
        super().validate(value)
        value = self.clean_up(value)
        if value is None:
            return
        value = str(value)
        if len(value) < self.min_length:
            raise InvalidCellValue(f"Value for '{self.label}' is too short. Minimum length is {self.min_length}.")
        if len(value) > self.max_length:
            raise InvalidCellValue(f"Value for '{self.label}' is too long. Maximum length is {self.max_length}.")
        

class IntegerColumn(SpreadSheetColumn):
    def __init__(self, label: str, name: str, width: float, required: bool = False, letter: Optional[str] = None):
        super().__init__(label=label, name=name, type="numeric", width=width, var_type=int, letter=letter, required=required)

    def validate(self, value: Any):
        super().validate(value)
        
        if isinstance(value, str):
            try:
                value = int(value.strip())
            except ValueError:
                raise InvalidCellValue(f"Invalid value '{value}' for '{self.label}'. Must be an integer.")
    
    def clean_up(self, value: Any) -> int | None:
        if (value := super().clean_up(value)) is None:
            return None
        return int(value)


class FloatColumn(SpreadSheetColumn):
    def __init__(self, label: str, name: str, width: float, required: bool = False, letter: Optional[str] = None):
        super().__init__(label=label, name=name, type="numeric", width=width, var_type=float, letter=letter, required=required)

    def validate(self, value: Any):
        super().validate(value)
        if isinstance(value, str):
            try:
                value = float(value.strip())
            except ValueError:
                raise InvalidCellValue(f"Invalid value '{value}' for '{self.label}'.")
    
    def clean_up(self, value: Any) -> float | None:
        if (value := super().clean_up(value)) is None:
            return None
        return float(value)
    

class DropdownColumn(SpreadSheetColumn):
    def __init__(self, label: str, name: str, width: float, choices: list[Any], required: bool = False, letter: Optional[str] = None):
        super().__init__(label=label, name=name, type="dropdown", width=width, var_type=str, source=choices, letter=letter, required=required)

    def validate(self, value: Any):
        super().validate(value)

        if value not in self.source:
            if self.source is None:
                raise ValueError(f"Dropdown column '{self.label}' must have a source list of choices.")
            raise InvalidCellValue(f"Invalid value '{value}' for '{self.label}'. Must be one of: {', '.join(self.source)}")