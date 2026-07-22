import os
import io
from typing import Any, Generic, Literal, TypeVar, overload

import pandas as pd
from pydantic import BaseModel

from opengsync_db import models

from ...core.config import settings
from .BaseInputField import BaseInputField
from .spreadsheet import SpreadsheetInputField
from ..tables.spreadsheet import SpreadSheetColumn


class FileUpload(BaseModel):    
    filename: str
    content: bytes
    content_type: str
    size: int

_DataT = TypeVar("_DataT", FileUpload, FileUpload | None, covariant=True)


class FileInputField(BaseInputField, Generic[_DataT]):
    """File upload input field.

    Renders an HTML file input with optional file type restrictions.
    File validation (size, extension) is handled at the form level.

    During validation the middleware stores file data as a dict with keys
    ``filename``, ``content`` (bytes), ``content_type``, and ``size``.  Use the
    properties below to access them instead of indexing ``.data`` directly.

    When ``required=True`` the type variable is ``dict`` and ``.data`` is
    typed as ``dict``; when ``required=False`` it is ``dict | None``.
    """

    @overload
    def __init__(
        self: "FileInputField[FileUpload]",
        label: str,
        *,
        max_size_mb: int | None = 10,
        allowed_extensions: list[str] | None = None,
        description: str | None = None,
        required: Literal[True] = True,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "FileInputField[FileUpload | None]",
        label: str,
        *,
        max_size_mb: int | None = 10,
        allowed_extensions: list[str] | None = None,
        description: str | None = None,
        required: Literal[False],
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self,
        label: str,
        *,
        max_size_mb: int | None = 10,
        allowed_extensions: list[str] | None = None,
        description: str | None = None,
        default: Any = None,
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            template="components/inputs/file.html",
            type="file",
            default=default,
            pydantic_type=Any,
            description=description,
            required=required,
            hidden=hidden,
            read_only=read_only,
        )
        self.max_size_mb = max_size_mb
        self.allowed_extensions = allowed_extensions or []
        self.accept = (
            ",".join(f".{ext.lstrip('.')}" for ext in self.allowed_extensions)
            if self.allowed_extensions
            else ""
        )

    @property
    def data(self) -> _DataT:
        if self._validated:
            if self._data is None:
                return None  # type: ignore
            return FileUpload.model_validate(self._data, from_attributes=True)  # type: ignore
        return None  # type: ignore

    def save(self, media_file: models.MediaFile):
        if self.data is None:
            raise ValueError("No file data to save.")
        
        if media_file.uuid is None:
            raise ValueError("MediaFile must have a UUID before saving.")
        
        path = os.path.join(settings.app_config.media_folder, media_file.type.dir, f"{media_file.uuid}{media_file.extension}")
        
        if os.path.exists(path):
            raise FileExistsError(f"File already exists at {path}.")
        
        with open(path, "wb") as f:
            f.write(self.data.content)

_SpreadsheetDataT = TypeVar("_SpreadsheetDataT", pd.DataFrame, pd.DataFrame | None, covariant=True)


class SpreadsheetFileField(FileInputField, Generic[_SpreadsheetDataT]):
    """A spreadsheet field that accepts an uploaded file (xlsx, csv, tsv) instead of
    interactive table data from the frontend.

    Extends :class:`FileInputField` and uses composition with
    :class:`SpreadsheetInputField` for column definition and validation logic.

    Args:
        label: Field label shown in the UI.
        required: Whether the file is required.
        columns: Predefined column definitions (same as ``SpreadsheetInputField``).
        allowed_file_types: List of allowed file extensions (without dot), e.g.
            ``["csv", "tsv", "xlsx"]``. Defaults to ``["csv", "tsv", "xlsx"]``.
        sheet_name: Name or index of the sheet to read when ``xlsx`` is allowed.
            **Required** if ``"xlsx"`` is in ``allowed_file_types``.
        can_be_empty: Whether an empty spreadsheet (no data rows) is acceptable.
        style: Optional CSS style dict passed to the internal spreadsheet.
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
        allowed_extensions = [
            ft.lower().lstrip(".") for ft in (allowed_file_types or ["csv", "tsv", "xlsx"])
        ]

        if "xlsx" in allowed_extensions and sheet_name is None:
            raise ValueError(
                "sheet_name must be provided when 'xlsx' is in allowed_file_types."
            )

        super().__init__(
            label=label,
            required=required,
            allowed_extensions=allowed_extensions,
        )
        self.template = "components/inputs/spreadsheet-file.html"

        # Internal spreadsheet for column management and validation
        self._spreadsheet = SpreadsheetInputField(
            label=label,
            required=required,
            columns=columns,
            can_be_empty=can_be_empty,
            style=style or {},
        )
        self._spreadsheet._configured = True

        self.sheet_name: str | int | None = sheet_name
        self.can_be_empty = can_be_empty

        # Populated after validate()
        self.file_bytes: bytes = b""
        self.file_filename: str = ""
        self.file_extension: str = ""

        # Comma-separated accept string for the HTML <input type="file">
        self.accept_extensions: str = ", ".join(f".{ft}" for ft in allowed_extensions)

    # ── Spreadsheet delegation ──────────────────────────────────────────

    @property
    def columns(self) -> dict[str, SpreadSheetColumn]:
        return self._spreadsheet.columns

    @property
    def table_data(self) -> list[list]:
        return self._spreadsheet.table_data

    @table_data.setter
    def table_data(self, value: list[list]) -> None:
        self._spreadsheet.table_data = value

    @property
    def to_delete(self) -> set[str]:
        return self._spreadsheet.to_delete

    @to_delete.setter
    def to_delete(self, value: set[str]) -> None:
        self._spreadsheet.to_delete = value

    @property
    def style(self) -> dict[str, str]:
        return self._spreadsheet.style

    @style.setter
    def style(self, value: dict[str, str]) -> None:
        self._spreadsheet.style = value

    @property
    def _errors(self) -> list[str]:
        return self._spreadsheet._errors

    @_errors.setter
    def _errors(self, value: list[str]) -> None:
        self._spreadsheet._errors = value

    def add_column(self, column: SpreadSheetColumn) -> None:
        self._spreadsheet.add_column(column)

    def set_data(self, df: pd.DataFrame) -> None:
        self._spreadsheet.set_data(df)

    def configure(
        self,
        csrf_token: str,
        df: pd.DataFrame = pd.DataFrame(),
        post_url: Any = None,
    ) -> None:
        self._spreadsheet.configure(csrf_token=csrf_token, df=df, post_url=post_url)

    def add_error(self, idx: Any, column: str | list[str], exception: Any) -> None:
        self._spreadsheet.add_error(idx, column, exception)
        # Keep self.errors in sync so form.errors picks them up
        self.errors = list(self._spreadsheet.errors)

    def add_general_error(self, message: str) -> None:
        self._spreadsheet.add_general_error(message)
        self.errors = list(self._spreadsheet.errors)

    # ── Data property override ──────────────────────────────────────────

    @property
    def data(self) -> _SpreadsheetDataT:
        """Validated spreadsheet data as a DataFrame."""
        return self._spreadsheet.data  # type: ignore

    @data.setter
    def data(self, value: Any) -> None:
        self._spreadsheet.data = value

    # ── Validation ──────────────────────────────────────────────────────

    def validate(self, raw_data: dict[str, Any]) -> bool:
        """Parse and validate an uploaded file against the configured columns.

        The only difference from :class:`SpreadsheetInputField` is the input
        source: this reads a file (xlsx/csv/tsv) instead of interactive table
        data from the frontend.  Column validation is delegated to the shared
        ``_validate_dataframe`` method.

        The raw upload is stored in ``self._data`` as a ``FileUpload``-compatible
        dict so that ``FileInputField.data`` returns a ``FileUpload`` object.
        """
        self._self_validated = True
        self._spreadsheet._errors = []
        self.errors = []
        self._spreadsheet.style = {}
        self._spreadsheet.to_delete = set()
        self._spreadsheet._data = None
        self._spreadsheet._validated = False
        self._data = None
        self._validated = False
        self.file_bytes = b""
        self.file_filename = ""
        self.file_extension = ""

        upload_file = raw_data.get(self.name)

        # Handle missing or empty file upload
        if upload_file is None or (hasattr(upload_file, "filename") and not upload_file.filename):
            if self.required:
                self._errors.append(f"{self.label} is required.")
                self.errors = list(self._errors)
                return False
            # Optional and not provided — return empty DataFrame
            self._spreadsheet._data = pd.DataFrame()
            self._spreadsheet._validated = True
            self.errors = []
            return True

        # Determine file extension
        filename = upload_file.filename if hasattr(upload_file, "filename") else str(upload_file)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext not in self.allowed_extensions:
            self._errors.append(
                f"File type '.{ext}' is not allowed. "
                f"Allowed types: {', '.join(self.allowed_extensions)}."
            )
            self.errors = list(self._errors)
            return False

        # Read the raw bytes from the upload
        file_obj = upload_file.file if hasattr(upload_file, "file") else upload_file
        try:
            content = file_obj.read() if hasattr(file_obj, "read") else b""
        except Exception as e:
            self._errors.append(f"Failed to read file '{filename}': {e}")
            self.errors = list(self._errors)
            return False

        # Store as FileUpload so FileInputField.data returns a FileUpload
        self._data = {
            "filename": filename,
            "content": content,
            "content_type": getattr(upload_file, "content_type", ""),
            "size": len(content),
        }
        self._validated = True

        # Also store for external access (used by UploadLibraryPrepSpreadsheetAction)
        self.file_bytes = content
        self.file_filename = filename
        self.file_extension = ext

        # Parse the bytes into a DataFrame based on extension
        try:
            data_stream = io.BytesIO(content)

            if ext == "xlsx":
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

        # Delegate to the same column validation SpreadsheetInputField uses
        col_names = [str(c) for c in df.columns]
        result = self._spreadsheet._validate_dataframe(df, col_names)
        self.errors = list(self._errors)
        return result

    def render(self, container_class: str = "", hide_label: bool = False, **kwargs) -> str:
        return BaseInputField.render(self, container_class=container_class, hide_label=hide_label, **kwargs)