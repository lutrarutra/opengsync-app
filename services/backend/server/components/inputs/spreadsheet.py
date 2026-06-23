import json
import string
from typing import Hashable, Generic, TypeVar

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
    data: _DataT

    def __init__(
        self,
        label: str = "Spreadsheet",
        required: bool = False,
        height: str | None = "600px",
        style: dict[str, str] | None = None,
        columns: list[SpreadSheetColumn] | None = None,
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
        self.raw_data: list[list] = []
        self.post_url: responses.URL | None = None
        self.csrf_token: str = ""
        self.editable: bool = False
        self.allow_new_cols: str = "false"
        self.allow_new_rows: str = "false"
        self.allow_col_rename: str = "false"
        self.min_spare_rows: int = 0
        self._errors: list[str] = []
        self.to_delete: set[str] = set()
        self.can_be_empty: bool = False
        self.style: dict[str, str] = style or {}
        self._configured: bool = False

        for col in columns or []:
            self.add_column(col)

    def add_column(self, column: SpreadSheetColumn) -> None:
        """Add a column to the spreadsheet.

        Can be called before or after ``configure()``. Column letters are
        (re)assigned based on the current column order.
        """
        if column.label in self.columns:
            raise ValueError(f"Column with label '{column.label}' already exists.")
        self.columns[column.label] = column
        self._reassign_letters()

    def _reassign_letters(self) -> None:
        """Reassign spreadsheet column letters (A, B, C, ...) based on insertion order."""
        for i, col in enumerate(self.columns.values()):
            col.letter = string.ascii_uppercase[i]

    def configure(
        self,
        df: pd.DataFrame,
        post_url: responses.URL,
        csrf_token: str,
        editable: bool = False,
        predefined_columns: list[SpreadSheetColumn] | None = None,
        allow_new_cols: bool = False,
        allow_new_rows: bool = False,
        allow_col_rename: bool = False,
        can_be_empty: bool = False,
    ):
        """Build the spreadsheet data from a DataFrame and configuration.

        Columns provided via the constructor or ``add_column()`` are preserved.
        Any additional ``predefined_columns`` passed here are merged in (duplicates
        by label are skipped). Columns from the DataFrame that are not already
        defined are auto-created as ``TextColumn`` instances.
        """
        self.post_url = post_url
        self.csrf_token = csrf_token
        self.editable = editable
        self.allow_new_cols = "true" if allow_new_cols else "false"
        self.allow_new_rows = "true" if allow_new_rows else "false"
        self.allow_col_rename = "true" if allow_col_rename else "false"
        self.min_spare_rows = 10 if allow_new_rows else 0
        self.can_be_empty = can_be_empty
        self._errors = []
        self.to_delete = set()
        self.style = {}

        existing_labels = set(self.columns.keys())

        for col in predefined_columns or []:
            if col.label in existing_labels:
                continue
            self.add_column(col)

        existing_labels = set(self.columns.keys())

        for col_name in df.columns:
            if col_name in existing_labels:
                continue
            col = TextColumn(
                col_name,
                col_name.replace("_", " ").title(),
                200,
                max_length=1000,
                read_only=not editable,
                can_be_deleted=editable,
            )
            self.add_column(col)

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

        self.raw_data = raw_data
        self._configured = True

    def validate(self, spreadsheet_json: str, columns_json: str) -> bool:
        """Parse and validate the spreadsheet data submitted from the frontend.

        Args:
            spreadsheet_json: JSON string of the 2D data array from jspreadsheet.
            columns_json: JSON string of comma-separated column header names.

        Returns:
            True if validation succeeded, False otherwise. Errors are collected
            in ``self._errors`` and cell-level styling in ``self.style``.
            The validated DataFrame is stored in ``self.data``.
        """
        if not self._configured:
            raise ValueError("SpreadsheetInputField has not been configured — call configure() first.")

        self._errors = []
        self.style = {}
        self.to_delete = set()
        self.data = None  # type: ignore

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

        col_title_map = {
            col.name: col.label for col in self.columns.values()
        }

        try:
            df = pd.DataFrame(data)
        except ValueError as e:
            self._errors.append(f"Invalid input: {e}")
            return False

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
                df[label] = df[label].astype(str)
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
                df[label] = df[label].astype(str)
            elif isinstance(column, IntegerColumn):
                df[label] = df[label].astype(pd.Int64Dtype())
            elif isinstance(column, FloatColumn):
                df[label] = df[label].astype(pd.Float64Dtype())

        self.data = df  # type: ignore
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