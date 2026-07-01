import json
import string
import io
from typing import Any, Hashable, Generic, Literal, TypeVar, overload

import pandas as pd
from loguru import logger
from uuid6 import uuid7

from .BaseInputField import BaseInputField
from ..tables.spreadsheet import (
    TextColumn,
    FloatColumn,
    IntegerColumn,
    DropdownColumn,
    CategoricalDropDown,
    SpreadSheetColumn,
    SpreadSheetException,
)
from ...core import responses


_DataT = TypeVar("_DataT", pd.DataFrame, pd.DataFrame | None, covariant=True)


class SpreadsheetInputField(BaseInputField, Generic[_DataT]):
    @overload
    def __init__(
        self: "SpreadsheetInputField[pd.DataFrame]",
        *,
        label: str = "Spreadsheet",
        required: Literal[True] = True,
        height: str | None = "600px",
        style: dict[str, str] | None = None,
        columns: list[SpreadSheetColumn] | None = None,
        allow_new_cols: bool = False,
        allow_new_rows: bool = True,
        allow_col_rename: bool = False,
        can_be_empty: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "SpreadsheetInputField[pd.DataFrame | None]",
        *,
        label: str = "Spreadsheet",
        required: Literal[False] = False,
        height: str | None = "600px",
        style: dict[str, str] | None = None,
        columns: list[SpreadSheetColumn] | None = None,
        allow_new_cols: bool = False,
        allow_new_rows: bool = True,
        allow_col_rename: bool = False,
        can_be_empty: bool = False,
    ) -> None: ...

    def __init__(
        self,
        label: str = "Spreadsheet",
        required: bool = False,
        height: str | None = "600px",
        style: dict[str, str] | None = None,
        columns: list[SpreadSheetColumn] | None = None,
        allow_new_cols: bool = False,
        allow_new_rows: bool = True,
        allow_col_rename: bool = False,
        can_be_empty: bool = False,
    ):
        super().__init__(
            label=label,
            template="components/inputs/spreadsheet.html",
            type="spreadsheet",
            required=required,
        )
        self.height = height
        self.id = uuid7().__str__()
        self.columns: dict[str, SpreadSheetColumn] = {}
        self.table_data: list[list] = []
        self.post_url: responses.URL | None = None
        self.csrf_token: str = ""
        self.editable: bool = False
        self.allow_new_cols: str = "true" if allow_new_cols else "false"
        self.allow_new_rows: str = "true" if allow_new_rows else "false"
        self.allow_col_rename: str = "true" if allow_col_rename else "false"
        self.min_spare_rows: int = 10 if allow_new_rows else 0
        self._errors: list[str] = []
        self.to_delete: set[str] = set()
        self.can_be_empty: bool = can_be_empty
        self.style: dict[str, str] = style or {}
        self._configured: bool = False

        for col in columns or []:
            self.add_column(col)

    @property
    def data(self) -> _DataT:
        """Validated spreadsheet data as a DataFrame.

        Returns the DataFrame if the spreadsheet has been validated.
        Raises ``ValueError`` if accessed before validation.
        """
        if not self._validated:
            raise ValueError(
                "Spreadsheet has not been validated yet. "
                "Call validate(raw_data) first."
            )
        return self._data  # type: ignore

    @data.setter
    def data(self, value: Any) -> None:
        self._data = value
        self._validated = True

    def add_column(self, column: SpreadSheetColumn) -> None:
        if column.label in self.columns:
            raise ValueError(f"Column with label '{column.label}' already exists.")
        self.columns[column.label] = column
        self._reassign_letters()

    def _reassign_letters(self) -> None:
        for i, col in enumerate(self.columns.values()):
            col.letter = string.ascii_uppercase[i]

    def configure(
        self,
        df: pd.DataFrame,
        csrf_token: str,
        post_url: responses.URL | None = None,
        predefined_columns: list[SpreadSheetColumn] | None = None,
    ):
        self.post_url = post_url
        self.csrf_token = csrf_token
        self._errors = []
        self.to_delete = set()
        self.style = {}

        existing_labels = set(self.columns.keys())

        for col in predefined_columns or []:
            if col.label in existing_labels:
                continue
            self.add_column(col)

        existing_labels = set(self.columns.keys())

        raw_data = []
        for _, row in df.iterrows():
            row_data = []
            for col in self.columns.values():
                val = row.get(col.label)
                if pd.isna(val):
                    row_data.append("")
                else:
                    row_data.append(str(val))
            raw_data.append(row_data)

        self.table_data = raw_data
        self._configured = True

    def validate(self, raw_data: dict[str, Any]) -> bool:
        if not self._configured:
            raise ValueError("SpreadsheetInputField has not been configured — call configure() first.")

        self._self_validated = True
        self._errors = []
        self.errors = []
        self.style = {}
        self.to_delete = set()
        self._data = None
        self._validated = False

        spreadsheet_json = str(raw_data.get("spreadsheet", "") or "")
        columns_json = str(raw_data.get("columns", "") or "")

        result = self._do_validate(spreadsheet_json, columns_json)
        self.errors = list(self._errors)
        return result

    def _do_validate(self, spreadsheet_json: str, columns_json: str) -> bool:
        """Internal validation logic for JSON table data. Delegates to ``_validate_dataframe``."""
        if not spreadsheet_json or not columns_json:
            self._errors.append("Spreadsheet data or columns are missing.")
            return False

        try:
            col_names = json.loads(columns_json)
            if isinstance(col_names, str):
                col_names = col_names.split(",")
            data = json.loads(spreadsheet_json)
        except (json.JSONDecodeError, TypeError) as e:
            self._errors.append(f"Invalid JSON payload: {e}")
            return False

        try:
            df = pd.DataFrame(data)
        except ValueError as e:
            self._errors.append(f"Invalid input: {e}")
            return False

        return self._validate_dataframe(df, col_names)

    def _validate_dataframe(self, df: pd.DataFrame, col_names: list[str]) -> bool:
        """Validate a DataFrame against the configured columns.

        Shared validation logic used by both ``SpreadsheetInputField`` (JSON
        table data from the frontend) and ``SpreadsheetFileField`` (uploaded
        file). Populates ``self._errors``, ``self.style``, and ``self.to_delete``.
        """
        col_title_map = {
            col.name: col.label for col in self.columns.values()
        }

        # Normalize whitespace / nulls
        df = df.replace(r"^\s*$", None, regex=True).map(
            lambda x: x.replace("\x00", "").strip() if isinstance(x, str) else x
        ).copy()

        # Map submitted header names to column labels
        df.columns = [
            col_title_map.get(c, c.lower().replace(" ", "_")) if isinstance(c, str) else c
            for c in col_names
        ]

        df = df.dropna(how="all")

        if len(df) == 0 and not self.can_be_empty:
            self._errors.append("Spreadsheet is empty.")
            return False

        # Track columns that have been removed by the user
        to_delete: set[str] = set()
        for label, column in self.columns.items():
            if column.can_be_deleted and label not in df.columns:
                to_delete.add(label)
            elif label not in df.columns:
                if column.required:
                    self._add_general_error(f"Missing required column: '{label}'")
        self.to_delete = to_delete

        # Type coercion + per-column validation
        for label, column in self.columns.items():
            if label not in df.columns:
                continue

            if isinstance(column, CategoricalDropDown):
                df[label] = df[label].astype(object)
            elif isinstance(column, TextColumn):
                df[label] = df[label].astype(pd.StringDtype())
            elif isinstance(column, DropdownColumn):
                df[label] = df[label].astype(object)

            if isinstance(column, DropdownColumn) and column.all_options_required:
                if column.source is None:
                    logger.error(f"Column '{label}' has no choices defined.")
                    raise ValueError(f"Column '{label}' has no choices defined.")
                for opt in column.source:
                    if opt not in df[label].unique():
                        self._add_general_error(
                            f"Column '{label}' has missing option '{opt}'. "
                            "You must use all options at least once."
                        )

            for idx, value in enumerate(df[label].tolist()):
                try:
                    if column.type == "text":
                        df[label] = df[label].apply(
                            lambda x: column.clean_up(x, ignore_missing=True)
                        )
                    column.validate(value, column_values=df[label].tolist())
                except SpreadSheetException as e:
                    self._add_error(idx, label, e)
                    continue

            if isinstance(column, IntegerColumn):
                df[label] = pd.to_numeric(df[label], errors="coerce").astype(pd.Int64Dtype())
            elif isinstance(column, FloatColumn):
                df[label] = pd.to_numeric(df[label], errors="coerce").astype(pd.Float64Dtype())

        if self._errors:
            return False

        # Final cleanup pass
        for label, column in self.columns.items():
            if label not in df.columns and column.can_be_deleted:
                continue
            if label not in df.columns:
                continue
            for idx, value in enumerate(df[label].tolist()):
                df.at[idx, label] = column.clean_up(value)

        if self._errors:
            return False

        # Final type coercion after cleanup
        for label, column in self.columns.items():
            if label not in df.columns:
                continue
            if isinstance(column, TextColumn):
                df[label] = df[label].astype(pd.StringDtype())
            elif isinstance(column, IntegerColumn):
                df[label] = df[label].astype(pd.Int64Dtype())
            elif isinstance(column, FloatColumn):
                df[label] = df[label].astype(pd.Float64Dtype())

        self._data = df
        self._validated = True
        return True

    def _add_error(self, idx: Hashable, column: str | list[str], exception: SpreadSheetException) -> None:
        """Record a cell-level error with styling and a human-readable message."""
        message = exception.message
        row_num = idx + 1  # type: ignore
        if isinstance(column, str):
            column = [column]
        for col in column:
            if col in self.columns:
                self.style[f"{self.columns[col].letter}{row_num}"] = f"background-color: {exception.color};"
        message = f"Row {row_num}: {message}"
        if message not in self._errors:
            self._errors.append(message)

    def _add_general_error(self, message: str) -> None:
        """Record a form-level error message."""
        if message not in self._errors:
            self._errors.append(message)

    async def render(self, container_class: str = "", submit_btn_id: str | None = None, target_element_id: str | None = None, hide_label: bool = False) -> str:
        return await super().render(container_class=container_class, hide_label=hide_label, submit_btn_id=submit_btn_id, target_element_id=target_element_id)


class SpreadsheetFileField(SpreadsheetInputField, Generic[_DataT]):
    data: _DataT

    """A spreadsheet field that accepts an uploaded file (xlsx, csv, tsv) instead of
    interactive table data from the frontend.

    The file is parsed into a DataFrame and validated against the same column
    definitions used by ``SpreadsheetInputField``.

    Args:
        label: Field label shown in the UI.
        required: Whether the file is required.
        columns: Predefined column definitions (same as ``SpreadsheetInputField``).
        allowed_file_types: List of allowed file extensions (without dot), e.g.
            ``["csv", "tsv", "xlsx"]``. Defaults to ``["csv", "tsv", "xlsx"]``.
        sheet_name: Name or index of the sheet to read when ``xlsx`` is allowed.
            **Required** if ``"xlsx"`` is in ``allowed_file_types``.
        can_be_empty: Whether an empty spreadsheet (no data rows) is acceptable.
        style: Optional CSS style dict (unused for file input rendering, but kept
            for compatibility with the shared validation logic).
    """

    @overload
    def __init__(
        self: "SpreadsheetFileField[pd.DataFrame]",
        *,
        label: str = "Spreadsheet File",
        required: Literal[True] = True,
        columns: list[SpreadSheetColumn] | None = None,
        allowed_file_types: list[str] | None = None,
        sheet_name: str | int | None = None,
        can_be_empty: bool = False,
        style: dict[str, str] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: "SpreadsheetFileField[pd.DataFrame | None]",
        *,
        label: str = "Spreadsheet File",
        required: Literal[False] = False,
        columns: list[SpreadSheetColumn] | None = None,
        allowed_file_types: list[str] | None = None,
        sheet_name: str | int | None = None,
        can_be_empty: bool = False,
        style: dict[str, str] | None = None,
    ) -> None: ...

    def __init__(
        self,
        label: str = "Spreadsheet File",
        required: bool = False,
        columns: list[SpreadSheetColumn] | None = None,
        allowed_file_types: list[str] | None = None,
        sheet_name: str | int | None = None,
        can_be_empty: bool = False,
        style: dict[str, str] | None = None,
    ):
        super().__init__(
            label=label,
            required=required,
            columns=columns,
            style=style,
        )
        # Override template and type for file input rendering
        self.template = "components/inputs/spreadsheet-file.html"
        self.type = "file"

        # File-specific configuration
        self.allowed_file_types: list[str] = [
            ft.lower().lstrip(".") for ft in (allowed_file_types or ["csv", "tsv", "xlsx"])
        ]

        if "xlsx" in self.allowed_file_types and sheet_name is None:
            raise ValueError(
                "sheet_name must be provided when 'xlsx' is in allowed_file_types."
            )

        self.sheet_name: str | int | None = sheet_name
        self.can_be_empty = can_be_empty

        # File fields don't need configure() — mark as ready for validation
        self._configured = True

        # Populated after validate() — raw bytes and metadata of the uploaded file
        self.file_bytes: bytes = b""
        self.file_filename: str = ""
        self.file_extension: str = ""

        # Comma-separated accept string for the HTML <input type="file">
        self.accept_extensions: str = ", ".join(f".{ft}" for ft in self.allowed_file_types)

    def validate(self, raw_data: dict[str, Any]) -> bool:
        """Parse and validate an uploaded file against the configured columns.

        Reads the file from ``raw_data[self.name]`` (a Starlette/FastAPI
        ``UploadFile``), parses it into a DataFrame based on the extension,
        and delegates to ``_validate_dataframe`` for column-level validation.
        """
        self._self_validated = True
        self._errors = []
        self.errors = []
        self.style = {}
        self.to_delete = set()
        self.file_bytes = b""
        self.file_filename = ""
        self.file_extension = ""
        self._data = None
        self._validated = False

        upload_file = raw_data.get(self.name)
        from loguru import logger
        logger.debug(upload_file)

        # Handle missing or empty file upload
        if upload_file is None or (hasattr(upload_file, "filename") and not upload_file.filename):
            if self.required:
                self._errors.append(f"{self.label} is required.")
                self.errors = list(self._errors)
                return False
            # Optional and not provided — return empty DataFrame
            self._data = pd.DataFrame()
            self._validated = True
            self.errors = []
            return True

        # Determine file extension
        filename = upload_file.filename if hasattr(upload_file, "filename") else str(upload_file)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext not in self.allowed_file_types:
            self._errors.append(
                f"File type '.{ext}' is not allowed. "
                f"Allowed types: {', '.join(self.allowed_file_types)}."
            )
            self.errors = list(self._errors)
            return False

        # Read the file into a DataFrame based on extension
        file_obj = upload_file.file if hasattr(upload_file, "file") else upload_file
        try:
            # Read raw bytes so we can store the original file and parse from a copy
            if hasattr(file_obj, "read"):
                self.file_bytes = file_obj.read()
            self.file_filename = filename
            self.file_extension = ext

            data_stream = io.BytesIO(self.file_bytes)

            if ext == "xlsx":
                # sheet_name is guaranteed to be set when xlsx is allowed
                df = pd.read_excel(data_stream, sheet_name=self.sheet_name)
                if isinstance(df, dict):
                    first_key = next(iter(df)) if df else None
                    if first_key is None:
                        self._errors.append(f"File '{filename}' has no sheets.")
                        self.errors = list(self._errors)
                        return False
                    df = df[first_key]
            elif ext == "csv":
                df = pd.read_csv(data_stream)
            elif ext == "tsv":
                df = pd.read_csv(data_stream, sep="\t")
            else:
                self._errors.append(f"Unsupported file type: '.{ext}'.")
                self.errors = list(self._errors)
                return False
        except Exception as e:
            self._errors.append(f"Failed to read file '{filename}': {e}")
            self.errors = list(self._errors)
            return False

        col_names = [str(c) for c in df.columns]
        result = self._validate_dataframe(df, col_names)
        self.errors = list(self._errors)
        return result

    async def render(self, container_class: str = "", hide_label: bool = False, **kwargs) -> str:
        return await BaseInputField.render(
            self, container_class=container_class, hide_label=hide_label, **kwargs
        )