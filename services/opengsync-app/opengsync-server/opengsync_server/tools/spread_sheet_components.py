import pandas as pd

from typing import Optional, Literal, Any, Type, Callable, Sequence

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


class NotUniqueCellValue(SpreadSheetException):
    def __init__(self, message: str):
        super().__init__(message, "#D5F5E3", "Not Unique Value")


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
    optional_col: bool = False
    unique: bool = False
    read_only: bool = False
    validation_fnc: Optional[Callable[[str], str | None]] = None

    def clean_up(self, value: Any, ignore_missing: bool = False) -> Any:
        if pd.isna(value):
            if self.required and not ignore_missing:
                logger.error(f"Value for '{self.label}' is required but missing.")
                raise ValueError(f"Value for '{self.label}' is required but missing.")
            return None
        
        if isinstance(value, str):
            if not (value := value.strip()) and self.required:
                raise MissingCellValue(f"Value for '{self.label}' is required but missing.")
            
            if not value:
                value = None

        if self.type == "text":
            value = str(value) if value is not None else None
                
        if self.clean_up_fnc is not None:
            return self.clean_up_fnc(value)
            
        return value
    
    def validate(self, value: Any, column_values: Sequence[Any]):
        if self.required and value is None:
            raise MissingCellValue(f"Missing value for '{self.label}'")
        
        if self.unique and value is not None:
            if column_values.count(self.clean_up(value)) > 1:
                raise DuplicateCellValue(f"Value '{value}' for '{self.label}' is not unique. It appears multiple times in the column.")

class TextColumn(SpreadSheetColumn):
    def __init__(
        self, label: str, name: str, width: float, max_length: int = 1024, min_length: int = 0,
        required: bool = False, optional_col: bool = False, clean_up_fnc: Optional[Callable] = None,
        letter: Optional[str] = None, unique: bool = False, read_only: bool = False, validation_fnc: Optional[Callable] = None
    ):
        super().__init__(
            label=label, name=name, type="text", width=width, var_type=str, clean_up_fnc=clean_up_fnc,
            letter=letter, required=required, optional_col=optional_col, unique=unique, read_only=read_only, validation_fnc=validation_fnc
        )
        self.max_length = max_length
        self.min_length = min_length

    def validate(self, value: Any, column_values: Sequence[Any]):
        super().validate(value, column_values)
        if pd.isna(value):
            if self.required:
                raise MissingCellValue(f"Missing value for '{self.label}'")
            return
        value = self.clean_up(value)
        value = str(value)
        if len(value) < self.min_length:
            raise InvalidCellValue(f"Value for '{self.label}' is too short. Minimum length is {self.min_length}.")
        if len(value) > self.max_length:
            raise InvalidCellValue(f"Value for '{self.label}' is too long. Maximum length is {self.max_length}.")
        
        if self.validation_fnc is not None:
            if self.clean_up_fnc is not None:
                value = self.clean_up_fnc(value)
            if (error := self.validation_fnc(value)) is not None:
                raise InvalidCellValue(f"Validation failed for '{self.label}': {error}")


class IntegerColumn(SpreadSheetColumn):
    def __init__(
        self, label: str, name: str, width: float, required: bool = False, letter: Optional[str] = None,
        optional_col: bool = False, unique: bool = False, read_only: bool = False
    ):
        super().__init__(
            label=label, name=name, type="numeric", width=width, var_type=int, letter=letter, required=required,
            optional_col=optional_col, unique=unique, read_only=read_only
        )

    def validate(self, value: Any, column_values: Sequence[Any]):
        super().validate(value, column_values)
        
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
    def __init__(
        self, label: str, name: str, width: float, required: bool = False, letter: Optional[str] = None,
        optional_col: bool = False, unique: bool = False, read_only: bool = False
    ):
        super().__init__(
            label=label, name=name, type="numeric", width=width, var_type=float, letter=letter,
            required=required, optional_col=optional_col, unique=unique, read_only=read_only
        )

    def validate(self, value: Any, column_values: Sequence[Any]):
        super().validate(value, column_values)
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
    all_options_required: bool

    def __init__(
        self, label: str, name: str, width: float, choices: list[Any], required: bool = False,
        letter: Optional[str] = None, optional_col: bool = False, unique: bool = False, all_options_required: bool = False, read_only: bool = False
    ):
        super().__init__(
            label=label, name=name, type="dropdown", width=width, var_type=str, source=choices,
            letter=letter, required=required, optional_col=optional_col, unique=unique, read_only=read_only
        )
        self.all_options_required = all_options_required

    def validate(self, value: Any, column_values: Sequence[Any]):
        super().validate(value, column_values)

        if value not in self.source:
            if pd.isna(value) and not self.required:
                return
            if self.source is None:
                raise ValueError(f"Dropdown column '{self.label}' must have a source list of choices.")
            raise InvalidCellValue(f"Invalid value '{value}' for '{self.label}'. Must be one of: {', '.join(self.source)}")
        

class CategoricalDropDown(SpreadSheetColumn):
    def __init__(
        self, label: str, name: str, width: float, categories: dict[Any, str], required: bool = False,
        letter: Optional[str] = None, optional_col: bool = False, unique: bool = False, read_only: bool = False
    ):
        super().__init__(
            label=label, name=name, type="dropdown", width=width, var_type=str,
            source=list(categories.values()), letter=letter, required=required,
            optional_col=optional_col, unique=unique, read_only=read_only
        )
        self.categories = categories
        self.rev_categories = {v: k for k, v in categories.items()}

    def validate(self, value: Any, column_values: Sequence[Any]):
        super().validate(value, column_values)
        if pd.isna(value) and not self.required:
            return
        if value not in self.rev_categories:
            raise InvalidCellValue(f"Invalid category '{value}' for '{self.label}'.")
        
    def clean_up(self, value: Any) -> Any:
        if pd.isna(value):
            return None
        return self.rev_categories[value]