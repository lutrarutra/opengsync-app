import numbers
from typing import Optional, Literal, Any, Type, Callable, Iterable, Sequence, cast
from dataclasses import dataclass

import pandas as pd
from loguru import logger
from starlette.datastructures import URL



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
    type: Literal["text", "numeric", "dropdown", "query"]
    width: float
    var_type: Type
    source: Optional[Any] = None
    clean_up_fnc: Optional[Callable] = None
    letter: str | None = None
    required: bool = False
    optional_col: bool = False
    unique: bool = False
    read_only: bool = False
    validation_fnc: Optional[Callable[[str], str | None]] = None
    can_be_deleted: bool = False

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
        if self.required and pd.isna(value):
            raise MissingCellValue(f"Missing value for '{self.label}'")
        
        if self.unique and pd.notna(value):
            if column_values.count(self.clean_up(value, ignore_missing=True)) > 1:
                raise DuplicateCellValue(f"Value '{value}' for '{self.label}' is not unique. It appears multiple times in the column.")

    def set_choices(self, choices: list[Any] | Callable[[], list[Any]]) -> None:
        raise NotImplementedError("set_choices must be implemented in subclasses that support choices.")

    def set_categories(self, categories: dict[Any, str]) -> None:
        """Update dropdown categories. Override in subclasses with category logic."""
        raise NotImplementedError("set_categories must be implemented in subclasses that support categories.")

class TextColumn(SpreadSheetColumn):
    def __init__(
        self, label: str, name: str, width: float, max_length: int = 1024, min_length: int = 0,
        required: bool = False, optional_col: bool = False, clean_up_fnc: Optional[Callable] = None,
        letter: str | None = None, unique: bool = False, read_only: bool = False, validation_fnc: Optional[Callable] = None,
        can_be_deleted: bool = False
    ):
        super().__init__(
            label=label, name=name, type="text", width=width, var_type=str, clean_up_fnc=clean_up_fnc,
            letter=letter, required=required, optional_col=optional_col, unique=unique, read_only=read_only, validation_fnc=validation_fnc,
            can_be_deleted=can_be_deleted
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
        self, label: str, name: str, width: float, required: bool = False, letter: str | None = None,
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
        self, label: str, name: str, width: float, required: bool = False, letter: str | None = None,
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
        self, label: str, name: str, width: float, choices: list[Any] | Callable[[], list[Any]], required: bool = False,
        letter: str | None = None, optional_col: bool = False, unique: bool = False, all_options_required: bool = False, read_only: bool = False
    ):
        super().__init__(
            label=label, name=name, type="dropdown", width=width, var_type=str,
            source=[] if callable(choices) else choices,
            letter=letter, required=required, optional_col=optional_col, unique=unique, read_only=read_only
        )
        self.all_options_required = all_options_required
        self._choices_factory: Callable[[], list[Any]] | None = choices if callable(choices) else None
        if self._choices_factory is not None:
            self.source = []

    def _ensure_choices(self) -> None:
        if self._choices_factory is not None and not self.source:
            self.source = self._choices_factory()

    def set_choices(self, choices: list[Any] | Callable[[], list[Any]]) -> None:
        """Update the dropdown choices after construction."""
        self._choices_factory = choices if callable(choices) else None
        self.source = [] if callable(choices) else choices

    def validate(self, value: Any, column_values: Sequence[Any]):
        self._ensure_choices()
        super().validate(value, column_values)

        if value not in self.source:
            if pd.isna(value) and not self.required:
                return
            if self.source is None:
                raise ValueError(f"Dropdown column '{self.label}' must have a source list of choices.")
            raise InvalidCellValue(f"Invalid value '{value}' for '{self.label}'. Must be one of: {', '.join(self.source)}")
        

class CategoricalDropDown(SpreadSheetColumn):
    def __init__(
        self, label: str, name: str, width: float, categories: dict[Any, str] | Callable[[], dict[Any, str]], required: bool = False,
        letter: str | None = None, optional_col: bool = False, unique: bool = False, read_only: bool = False
    ):
        super().__init__(
            label=label, name=name, type="dropdown", width=width, var_type=str,
            source=[] if callable(categories) else list(categories.values()), letter=letter, required=required,
            optional_col=optional_col, unique=unique, read_only=read_only
        )
        self._categories_factory: Callable[[], dict[Any, str]] | None = categories if callable(categories) else None
        self.categories: dict[Any, str] = (
            {} if self._categories_factory is not None else cast(dict[Any, str], categories)
        )
        self.rev_categories = {v: k for k, v in self.categories.items()}

    def _ensure_categories(self) -> None:
        if self._categories_factory is not None and not self.categories:
            self.set_categories(self._categories_factory())

    def set_categories(self, categories: dict[Any, str]) -> None:
        """Update the dropdown categories after construction.

        Updates ``categories``, ``rev_categories``, and ``source`` together
        so that the frontend dropdown, validation, and display all stay
        consistent.
        """
        self.categories = categories
        self.rev_categories = {v: k for k, v in categories.items()}
        self.source = list(categories.values())

    def validate(self, value: Any, column_values: Sequence[Any]):
        self._ensure_categories()
        super().validate(value, column_values)
        if pd.isna(value) and not self.required:
            return
        if value not in self.rev_categories:
            raise InvalidCellValue(f"Invalid category '{value}' for '{self.label}'.")
        
    def clean_up(self, value: Any) -> Any:
        self._ensure_categories()
        if pd.isna(value):
            return None
        return self.rev_categories[value]

    def to_display(self, value: Any) -> Any:
        """Convert a stored key back to the human-readable display name."""
        if pd.isna(value):
            return None
        return self.categories.get(value, None)


class DBObjectColumn(CategoricalDropDown):
    """Render an object's id and name DataFrame columns as one selectable "name [id]" column.

    Objects that are not created yet (``new_names`` of ``set_categories``) are shown as "name [new]" and keep an
    empty id.
    """

    NEW_ID = "new"

    def __init__(
        self,
        columns: tuple[str, str],
        label: str,
        width: float,
        categories: dict[Any, str] | Callable[[], dict[Any, str]],
        required: bool = False,
        unique: bool = False,
        all_options_required: bool = False,
        read_only: bool = False,
    ):
        if len(columns) != 2:
            raise ValueError("DBObjectColumn requires an id and a name DataFrame column.")
        super().__init__(label, label, width, categories, required, unique=unique, read_only=read_only)
        self.backend_columns = columns
        self.all_options_required = all_options_required
        self.new_values: list[str] = []

    def new_value(self, name: str) -> str:
        return f"{name} [{self.NEW_ID}]"

    def set_categories(self, categories: dict[Any, str], new_names: Sequence[str] = ()) -> None:
        """Set the options, ``new_names`` are options of objects without id."""
        super().set_categories(categories)
        self.new_values = [self.new_value(name) for name in new_names]
        self.source = self.source + self.new_values

    def cast_backend_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cast the id column to Int64 and the name column to string."""
        id_column, name_column = self.backend_columns
        if id_column in df.columns:
            df[id_column] = df[id_column].astype(pd.Int64Dtype())
        if name_column in df.columns:
            df[name_column] = df[name_column].astype(pd.StringDtype())
        return df

    def validate(self, value: Any, column_values: Sequence[Any]):
        self._ensure_categories()
        if pd.isna(value):
            if self.required:
                raise MissingCellValue(f"Missing value for '{self.label}'")
            return
        options = self.categories or self.new_values
        if options and value not in self.rev_categories and value not in self.new_values:
            raise InvalidCellValue(f"Invalid value '{value}' for '{self.label}'.")
        if self.unique and list(column_values).count(value) > 1:
            raise DuplicateCellValue(f"Value '{value}' for '{self.label}' is not unique. It appears multiple times in the column.")

    def to_display_row(self, row: pd.Series) -> Any:
        self._ensure_categories()
        object_id = row.get(self.backend_columns[0])
        object_name = row.get(self.backend_columns[1])
        if pd.isna(object_id):
            if pd.notna(object_name) and (new_value := self.new_value(object_name)) in self.new_values:
                return new_value
            return None
        # Use the category value as the canonical frontend value so restored
        # data round-trips exactly like a value selected in the dropdown.
        display_value = self.categories.get(object_id)
        if display_value is not None:
            return display_value
        return f"{object_name} [{object_id}]" if pd.notna(object_name) else f"[{object_id}]"

    def expand(self, value: Any) -> dict[str, Any]:
        if pd.isna(value):
            return {column: None for column in self.backend_columns}
        text = str(value)
        # Expected format: "name [id]"
        name, separator, identifier = text.rpartition(" [")
        if not separator or not identifier.endswith("]"):
            raise InvalidCellValue(f"Invalid value '{value}' for '{self.label}'.")
        if text in self.new_values:
            return {self.backend_columns[0]: None, self.backend_columns[1]: name.strip()}
        try:
            object_id = int(identifier[:-1])
        except ValueError as error:
            raise InvalidCellValue(f"Invalid ID in '{value}' for '{self.label}'.") from error
        return {self.backend_columns[0]: object_id, self.backend_columns[1]: name.strip()}


class QueryColumn(SpreadSheetColumn):
    """Column whose options are searched on the backend instead of being sent with the page.

    The cell shows the option name and submits its id. The editor requests ``url`` with ``word`` and ``page``
    and expects ``responses.query_options_response``, without ``url`` there are no options to pick. ``lookup``
    returns the names of the given ids that the user may select: it names the ids shown in the table and rejects
    submitted ids that are unknown or not allowed.

    ``name_column`` adds a DataFrame column with the name of each option. With ``allow_new`` a cell may also hold
    text that is none of the options: a new value, validated and cleaned up by ``name_column``, whose id is empty.
    """

    def __init__(
        self, label: str, name: str, width: float,
        url: URL | Callable[[], URL | None] | None,
        lookup: Callable[[Sequence[int]], dict[int, str]],
        required: bool = False, letter: str | None = None, optional_col: bool = False, unique: bool = False,
        read_only: bool = False, allow_new: bool = False, name_column: TextColumn | None = None,
    ):
        if allow_new and name_column is None:
            raise ValueError("A QueryColumn with allow_new needs a name_column for the new values.")
        super().__init__(
            label=label, name=name, type="query", width=width, var_type=int,
            letter=letter, required=required, optional_col=optional_col, unique=unique, read_only=read_only,
        )
        self._url = url
        self.lookup = lookup
        self.allow_new = allow_new
        self.name_column = name_column
        self.labels: dict[int, str] = {}

    @property
    def url(self) -> URL | None:
        return self._url() if callable(self._url) else self._url

    def set_url(self, url: URL | Callable[[], URL | None] | None) -> None:
        """Change the queried route, e.g. to add query parameters from the request context."""
        self._url = url

    @staticmethod
    def to_id(value: Any) -> int | None:
        """The id in a cell, None for empty cells and text that was not resolved to an option."""
        if isinstance(value, bool) or pd.isna(value):
            return None
        if isinstance(value, numbers.Integral):
            return int(value)
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None

    def new_value(self, value: Any) -> str | None:
        """The cleaned up text of a new value, None for ids, empty cells and columns without new values."""
        if not self.allow_new or not isinstance(value, str) or not value.strip():
            return None
        return cast(TextColumn, self.name_column).clean_up(value, ignore_missing=True)

    def _unique_key(self, value: Any) -> int | str | None:
        """Cells are duplicates when their ids or the cleaned up texts of their new values are equal."""
        object_id = self.to_id(value)
        return object_id if object_id is not None else self.new_value(value)

    def to_name(self, value: Any) -> str | None:
        """The option name of an id, or the text of a new value."""
        if (object_id := self.to_id(value)) is not None:
            return self.labels.get(object_id)
        return self.new_value(value)

    def to_display(self, df: pd.DataFrame) -> list[Any]:
        """Cell values of a DataFrame with this column and maybe ``name_column``: ids, and the names of new values."""
        ids = df[self.label].tolist() if self.label in df.columns else [None] * len(df)
        names = [None] * len(df)
        if self.allow_new and (name_label := cast(TextColumn, self.name_column).label) in df.columns:
            names = df[name_label].tolist()
        self.set_labels(ids)
        return [
            object_id if (object_id := self.to_id(value)) is not None else ("" if pd.isna(name) else name)
            for value, name in zip(ids, names)
        ]

    def set_labels(self, values: Iterable[Any]) -> None:
        """Look up the names of the ids in the table."""
        ids = sorted({object_id for value in values if (object_id := self.to_id(value)) is not None})
        self.labels = self.lookup(ids) if ids else {}

    def validate(self, value: Any, column_values: Sequence[Any]):
        if pd.isna(value):
            if self.required:
                raise MissingCellValue(f"Missing value for '{self.label}'")
            return
        if (object_id := self.to_id(value)) is not None:
            if object_id not in self.labels:
                raise InvalidCellValue(f"Unknown {self.name.lower()} '{value}'.")
        elif self.allow_new and isinstance(value, str):
            cast(TextColumn, self.name_column).validate(value, [])
        else:
            raise InvalidCellValue(f"Unknown {self.name.lower()} '{value}'.")
        if self.unique:
            if [self._unique_key(v) for v in column_values].count(self._unique_key(value)) > 1:
                raise DuplicateCellValue(f"Value '{value}' for '{self.label}' is not unique. It appears multiple times in the column.")

    def clean_up(self, value: Any, ignore_missing: bool = False) -> int | None:
        if pd.isna(value):
            return super().clean_up(value, ignore_missing=ignore_missing)
        return self.to_id(value)
