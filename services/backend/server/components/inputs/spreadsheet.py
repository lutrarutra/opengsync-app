import string

import pandas as pd
from uuid6 import uuid7

from .BaseInputField import BaseInputField
from ..tables.spreadsheet import TextColumn, SpreadSheetColumn


class SpreadsheetInputData:
    """Data container for the interactive Handsontable spreadsheet editor.
    Provides the interface expected by the spreadsheet.jinja2 template."""

    def __init__(
        self,
        columns: dict[str, SpreadSheetColumn],
        raw_data: list[list],
        post_url: str,
        csrf_token: str,
        editable: bool = False,
        allow_new_cols: bool = False,
        allow_new_rows: bool = False,
        allow_col_rename: bool = False,
        errors: list[str] | None = None,
    ):
        self.id = uuid7().__str__()
        self.columns = columns
        self._raw_data = raw_data
        self.post_url = post_url
        self.csrf_token = csrf_token
        self.editable = editable
        self.allow_new_cols = "true" if allow_new_cols else "false"
        self.allow_new_rows = "true" if allow_new_rows else "false"
        self.allow_col_rename = "true" if allow_col_rename else "false"
        self.min_spare_rows = 10 if allow_new_rows else 0
        self._errors = errors or []
        self.to_delete: set[str] = set()

    @property
    def raw_data(self) -> list[list]:
        return self._raw_data


class SpreadsheetInputField(BaseInputField):
    """Reusable input field for the interactive Handsontable spreadsheet editor.

    Use this field in any HTMXForm that needs an editable spreadsheet.
    Configure it in the form's prepare() method by calling configure().
    """

    def __init__(
        self,
        label: str = "Spreadsheet",
        required: bool = False,
        height: str | None = "1000px",
        style: dict[str, str] | None = None,
    ):
        super().__init__(
            label=label,
            template="components/inputs/spreadsheet.html",
            type="spreadsheet",
            required=required,
        )
        self.height = height
        self.style = style or {}
        self.data_obj: SpreadsheetInputData | None = None

    def configure(
        self,
        df: pd.DataFrame,
        post_url: str,
        csrf_token: str,
        editable: bool = False,
        predefined_columns: list[SpreadSheetColumn] | None = None,
        allow_new_cols: bool = False,
        allow_new_rows: bool = False,
        allow_col_rename: bool = False,
    ):
        """Build the spreadsheet data from a DataFrame and configuration."""
        columns: dict[str, SpreadSheetColumn] = {}

        for col in predefined_columns or []:
            col.letter = string.ascii_uppercase[len(columns)]
            columns[col.label] = col

        for col_name in df.columns:
            if col_name in [c.label for c in (predefined_columns or [])]:
                continue
            col = TextColumn(
                col_name,
                col_name.replace("_", " ").title(),
                200,
                max_length=1000,
                read_only=not editable,
                can_be_deleted=editable,
            )
            col.letter = string.ascii_uppercase[len(columns)]
            columns[col.label] = col

        raw_data = []
        for _, row in df.iterrows():
            row_data = []
            for col in columns.values():
                val = row.get(col.label)
                if pd.isna(val):
                    row_data.append("")
                else:
                    row_data.append(str(val))
            raw_data.append(row_data)

        self.data_obj = SpreadsheetInputData(
            columns=columns,
            raw_data=raw_data,
            post_url=post_url,
            csrf_token=csrf_token,
            editable=editable,
            allow_new_cols=allow_new_cols,
            allow_new_rows=allow_new_rows,
            allow_col_rename=allow_col_rename,
        )

    def __getattr__(self, name: str):
        """Proxy attribute access to the underlying SpreadsheetInputData."""
        if name in (
            "id",
            "columns",
            "raw_data",
            "post_url",
            "csrf_token",
            "min_spare_rows",
            "allow_new_cols",
            "allow_new_rows",
            "allow_col_rename",
            "style",
            "_errors",
            "to_delete",
            "editable",
        ):
            if self.data_obj is not None:
                return getattr(self.data_obj, name)
            raise AttributeError(
                f"SpreadsheetInputField has no '{name}' — call configure() first."
            )
        raise AttributeError(f"'SpreadsheetInputField' object has no attribute '{name}'")

    async def render(self, container_class: str = "", submit_btn_id: str | None = None, hide_label: bool = False) -> str:
        return await super().render(container_class=container_class, hide_label=hide_label, submit_btn_id=submit_btn_id)