from typing import Any, Hashable, Generic, Literal, TypeVar, overload
import json
import string
from uuid6 import uuid7

import numpy as np
import pandas as pd
from loguru import logger

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

    def set_data(self, df: pd.DataFrame):
        for col in self.columns.keys():
            if col not in df.columns:
                df[col] = None

        for col in self.columns.values():
            if isinstance(col, CategoricalDropDown):
                if col.label in df.columns:
                    df[col.label] = df[col.label].apply(lambda v, c=col: c.to_display(v))
        self.table_data = df[[col.label for col in self.columns.values()]].astype(object).replace(np.nan, "").values.tolist()

    def configure(
        self,
        csrf_token: str,
        df: pd.DataFrame = pd.DataFrame(),
        post_url: responses.URL | None = None,
    ):
        self.post_url = post_url
        self.csrf_token = csrf_token
        self._errors = []
        self.to_delete = set()
        self.style = {}
        self.set_data(df)
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
            self.table_data = df.replace(np.nan, "").values.tolist()
        except ValueError as e:
            self._errors.append(f"Invalid input: {e}")
            return False

        return self._validate_dataframe(df, col_names)

    def _validate_dataframe(self, df: pd.DataFrame, col_names: list[str]) -> bool:
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
                    self.add_general_error(f"Missing required column: '{label}'")
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
                        self.add_general_error(
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
                    self.add_error(idx, label, e)
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
        # Build table_data with display values for CategoricalDropDown columns
        # so the frontend dropdown cells show the human-readable label, not the key.
        table_df = df.copy()
        for col in self.columns.values():
            if isinstance(col, CategoricalDropDown):
                if col.label in table_df.columns:
                    table_df[col.label] = table_df[col.label].apply(
                        lambda v, c=col: c.to_display(v)
                    )
        self.table_data = table_df.replace(np.nan, "").values.tolist()
        self._validated = True
        return True

    def add_error(self, idx: Hashable, column: str | list[str], exception: SpreadSheetException) -> None:
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
        if message not in self.errors:
            self.errors.append(message)

    def add_general_error(self, message: str) -> None:
        """Record a form-level error message."""
        if message not in self._errors:
            self._errors.append(message)
        if message not in self.errors:
            self.errors.append(message)

    def render(self, container_class: str = "", submit_btn_id: str | None = None, target_element_id: str | None = None, hide_label: bool = False) -> str:
        return super().render(container_class=container_class, hide_label=hide_label, submit_btn_id=submit_btn_id, target_element_id=target_element_id)


